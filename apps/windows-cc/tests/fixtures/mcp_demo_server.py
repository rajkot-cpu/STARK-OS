from mcp.server.mcpserver import MCPServer as FastMCP
app=FastMCP("jarvis-trial")
@app.tool()
def add(a:int,b:int)->int:
    "Add two numbers"
    return a+b
@app.tool()
def time_ist()->str:
    "Current time in IST"
    import datetime; return datetime.datetime.now().isoformat()
if __name__=="__main__": app.run()
