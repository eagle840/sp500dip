# sp500dip













## Azure Deployment


```bash
az functionapp deployment source config \
  --name <FunctionAppName> \
  --resource-group <ResourceGroup> \
  --repo-url <GitHubRepoURL> \
  --branch main \
  --manual-integration
  ```
