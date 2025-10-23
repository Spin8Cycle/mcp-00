import asyncio
import os
import ast
from pathlib import Path
from typing import Optional
from contextlib import AsyncExitStack

from openai import AsyncOpenAI, OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from dotenv import load_dotenv


parent = Path(__file__).resolve().parent
load_dotenv(dotenv_path=parent / ".env", override=True)

default_url = os.getenv('LMSTUDIO_BASE_URL')
default_api_key = os.getenv('API_KEY')

client = OpenAI(base_url=default_url, api_key=default_api_key)

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.client = client

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

    Args:
        server_script_path: Path to the server script (.py or .js)
    """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))    
        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using LMStudio and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        tools = await self.session.list_tools()

        # format for openai api tool schema
        available_tools = [{
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        } for tool in tools.tools]

        # Initial OpenAI API call
        response = self.client.responses.create(
            model='ibm/granite-4-h-tiny',
            input = messages,
            tools=available_tools,
            tool_choice='auto'
        )
        
        # Process response and handle tool calls

        if output := response.output[0]:
            if output.type == 'function_call':
                tool_name = output.name
                tool_args = ast.literal_eval(output.arguments)
                tool_call = await self.session.call_tool(tool_name, tool_args)
                final_message = tool_call.content[0].text
            elif output.type == 'message':
                final_message = output.content[0].text
        else:
            final_message = "No response generated."
        return final_message

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery:\n\t").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print(f"ChatBot:\n\t{response}\n{'='*60}")

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():

    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)
    
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())