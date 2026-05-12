MCP Server and Client implementation to read apple watch data for analysis.

Connecting to Claude Desktop: Add an entry to ~/Library/Application Support/Claude/claude_desktop_config.json
```
{
     "mcpServers": {
       "apple-watch": {
         "command": "python",
         "args": ["/full/path/to/server.py", "/full/path/to/export.xml"]
       }
     }
}
```
