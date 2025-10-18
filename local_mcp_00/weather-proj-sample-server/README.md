# Using LM Studio as Client

Source: [Use MCP Servers](https://lmstudio.ai/docs/app/plugins/mcp)

1. Go to `Chats`
2. On the right side of the UI, select `Program`.
3. Click on `Install` dropdown.
4. Select `Edit mcp.json`
5. To add `weather-proj-sample-server`, add the following:

```json
{
  "mcpServers": {
    "weather-server": {
      "command": "uv",
      "args": [
        "--directory",
        "~\\local_mcp_00\\weather-proj-sample-server",
        "run",
        "weather.py"
      ]
    }
  }
}
```