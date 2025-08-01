import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anthropic import Anthropic 
from dotenv import load_dotenv

load_dotenv() #load environment variables from .env

#Basic Client Class
class MCPClient:
    def __init__(self):
        #Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic()
    
    #Method to connect to MCP Server
    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP Server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """

        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command = command,
            args = [server_script_path],
            env = None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        await self.session.initialize()

        #List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools: ", [tool.name for tool in tools])

    #Query Processing Logic - Handling tool calls
    async def process_query(self, query:str):
            """Process a query using Claude and available tools"""
            messages = [
                {
                    "role":"user",
                    "content": query
                }
            ]

            response = await self.session.list_tools()
            available_tools = [{
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            } for tool in response.tools]

            #Initial Claude API Call
            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens = 1000,
                messages = messages,
                tools = available_tools
            )

            #Process response and handle tool calls 
            final_text = []

            assistant_message_content = []
            for content in response.content:
                if content.type == 'text':
                    final_text.append(content.text)
                    assistant_message_content.append(content)
                elif content.type == 'tool_use':
                    tool_name = content.name
                    tool_args = content.input

                    #Execute tool call
                    result = await self.session.call_tool (tool_name, tool_args)
                    final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                    assistant_message_content.append(content)
                    messages.append({
                        "role": "assistant",
                        "content": assistant_message_content
                    })
                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": result.content
                            }
                        ]
                    })

                    #Get the next response from Claude
                    response = self.anthropic.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=1000,
                        messages=messages,
                        tools=available_tools
                    )

                    final_text.append(response.content[0].text)
            
            return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n"+response)

            except Exception as e:
                print(f"\nError: {str(e)}")
            
    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
        if len(sys.argv) < 2:
            print("Usage: python client.py C:\\Users\\Admin\\OneDrive\\Desktop\\weather\\weather.py")
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