import azure.functions as func
import yfinance as yf
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from azure.monitor.opentelemetry.exporter import AzureMonitorMetricExporter
from azure.storage.blob import BlobServiceClient
import os
import logging
import json

# Configure OpenTelemetry for Azure Monitor
configure_azure_monitor()

# Get the Application Insights connection string from environment variables
APPINSIGHTS_CONNECTION_STRING = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")

# Create a metric exporter
exporter = AzureMonitorMetricExporter.from_connection_string(APPINSIGHTS_CONNECTION_STRING)

# Create a metric reader
reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5000)

# Create a meter provider
provider = MeterProvider(metric_readers=[reader])

# Set the meter provider
metrics.set_meter_provider(provider)

# Create a meter
meter = metrics.get_meter_provider().get_meter("sp500_monitor")

# Create a counter instrument
sp500_change_metric = meter.create_gauge(
    "sp500_percentage_change",
    unit="percentage",
    description="The percentage change of the S&P 500 index.",
)

# Initialize the Function App
app = func.FunctionApp()

# Azure Blob Storage connection string
connect_str = os.environ.get("AzureWebJobsStorage")
container_name = "sp500-data"
blob_name = "last_price.json"

@app.schedule(schedule="0 0 18 * * 1-5", arg_name="myTimer", run_on_startup=False)
def sp500_monitor(myTimer: func.TimerRequest) -> None:
    """
    This function runs on a timer trigger (daily on weekdays at 6 PM UTC),
    fetches the S&P 500 price, calculates the percentage change from the
    previous day, and sends a custom metric to Azure Monitor.
    """
    if myTimer.past_due:
        logging.info("The timer is past due!")

    logging.info("Python timer trigger function ran at %s", myTimer.schedule_status['Last'])

    try:
        # Initialize Blob Service Client
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

        # Get the last stored price
        last_price = 0.0
        try:
            if blob_client.exists():
                downloader = blob_client.download_blob(max_concurrency=1, encoding="UTF-8")
                blob_data = downloader.readall()
                if blob_data:
                    data = json.loads(blob_data)
                    last_price = data.get("last_price", 0.0)
        except Exception as e:
            logging.error(f"Error reading from blob: {e}")


        # Get the current S&P 500 price
        sp500 = yf.Ticker("^GSPC")
        hist = sp500.history(period="1d")
        current_price = hist['Close'].iloc[-1]

        logging.info(f"Current S&P 500 Price: {current_price}")
        logging.info(f"Last Stored S&P 500 Price: {last_price}")


        # Calculate percentage change
        if last_price > 0:
            percentage_change = ((current_price - last_price) / last_price) * 100
            logging.info(f"S&P 500 Percentage Change: {percentage_change}%")

            # Send the metric to Azure Monitor
            sp500_change_metric.set(percentage_change)

            # Check for the 2% drop
            if percentage_change <= -2.0:
                logging.warning(f"S&P 500 has dropped by {percentage_change}%. An alert should be triggered.")

        # Store the current price for the next run
        try:
            blob_client.upload_blob(json.dumps({"last_price": current_price}), overwrite=True)
            logging.info("Successfully stored the current price to blob storage.")
        except Exception as e:
            logging.error(f"Error writing to blob: {e}")


    except Exception as e:
        logging.error(f"An error occurred: {e}")
