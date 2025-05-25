#!/usr/bin/env python3
"""
SMPTE Timecode Client
Interactive client for connecting to SMPTE Timecode Server.
"""

import asyncio
import json
import sys
import argparse
import re
from typing import Dict, Any, Optional
import aioconsole


class SMPTETimecodeClient:
    """SMPTE Timecode Client with interactive command interface."""
    
    def __init__(self, host: str = 'localhost', port: int = 8080):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        self.current_session: Optional[Dict[str, Any]] = None
        self.supported_framerates = []
        self.running = True
    
    async def connect(self):
        """Connect to the SMPTE server"""
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.connected = True
            print(f"Connected to SMPTE Timecode Server at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the server"""
        self.running = False
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.connected = False
        self.current_session = None
    
    async def send_command(self, command: Dict[str, Any]):
        """Send a command to the server"""
        if not self.connected or not self.writer:
            print("Not connected to server")
            return
        
        try:
            message = json.dumps(command) + '\n'
            self.writer.write(message.encode())
            await self.writer.drain()
        except Exception as e:
            print(f"Error sending command: {e}")
    
    async def handle_server_messages(self):
        """Handle incoming messages from the server"""
        try:
            while self.connected and self.running:
                if not self.reader:
                    break
                
                line = await self.reader.readline()
                if not line:
                    break
                
                try:
                    message = json.loads(line.decode().strip())
                    await self.handle_server_message(message)
                except json.JSONDecodeError:
                    print("Received invalid JSON from server")
                except Exception as e:
                    print(f"Error handling server message: {e}")
        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.connected = False
            self.current_session = None
    
    async def handle_server_message(self, message: Dict[str, Any]):
        """Process messages from the server"""
        msg_type = message.get('type')
        
        if msg_type == 'welcome':
            print(f"\n{message.get('message', 'Welcome')}")
            self.supported_framerates = message.get('supported_framerates', [])
            print(f"Supported framerates: {', '.join(self.supported_framerates)}")
            self.show_help()
        
        elif msg_type == 'session_created':
            self.current_session = {
                'id': message.get('session_id'),
                'framerate': message.get('framerate'),
                'role': 'creator'
            }
            print(f"\nSession created: {message.get('session_id')}")
            print(f"Framerate: {message.get('framerate')} fps")
            print(f"Initial timecode: {message.get('initial_timecode')}")
        
        elif msg_type == 'session_joined':
            self.current_session = {
                'id': message.get('session_id'),
                'framerate': message.get('framerate'),
                'role': 'participant'
            }
            print(f"\nJoined session: {message.get('session_id')}")
            print(f"Framerate: {message.get('framerate')} fps")
            print(f"Current timecode: {message.get('current_timecode')}")
            print(f"Status: {'Running' if message.get('running') else 'Stopped'}")
        
        elif msg_type == 'timecode_update':
            # Clear line and show timecode (overwrite previous line)
            framerate = self.current_session.get('framerate', '') if self.current_session else ''
            print(f"\r{message.get('timecode')} ({framerate} fps)", end='', flush=True)
        
        elif msg_type == 'timecode_started':
            print(f"\nTimecode started: {message.get('timecode')}")
        
        elif msg_type == 'timecode_stopped':
            print(f"\nTimecode stopped: {message.get('timecode')}")
            self.show_prompt()
        
        elif msg_type == 'timecode_reset':
            print(f"\nTimecode reset to: {message.get('timecode')}")
            self.show_prompt()
        
        elif msg_type == 'error':
            print(f"\nError: {message.get('message')}")
            self.show_prompt()
        
        else:
            print(f"\nReceived: {message}")
    
    async def handle_user_input(self):
        """Handle user input commands"""
        try:
            while self.running and self.connected:
                try:
                    # Show prompt
                    self.show_prompt()
                    
                    # Read user input
                    user_input = await aioconsole.ainput()
                    
                    if not user_input.strip():
                        continue
                    
                    await self.process_user_command(user_input.strip())
                
                except EOFError:
                    break
                except KeyboardInterrupt:
                    print("\nUse 'quit' to exit")
                    continue
        
        except asyncio.CancelledError:
            pass
    
    async def process_user_command(self, user_input: str):
        """Process user commands"""
        parts = user_input.split()
        if not parts:
            return
        
        command = parts[0].lower()
        
        if command == 'create':
            await self.create_session(parts)
        elif command == 'join':
            await self.join_session(parts)
        elif command == 'leave':
            await self.leave_session()
        elif command == 'start':
            await self.start_timecode()
        elif command == 'stop':
            await self.stop_timecode()
        elif command == 'reset':
            await self.reset_timecode(parts)
        elif command == 'status':
            self.show_status()
        elif command == 'help':
            self.show_help()
        elif command in ['quit', 'exit']:
            print("Goodbye!")
            await self.disconnect()
        else:
            print("Unknown command. Type 'help' for available commands.")
    
    async def create_session(self, parts):
        """Create a new session"""
        if len(parts) < 2:
            print("Usage: create <framerate> [initial_timecode]")
            print(f"Available framerates: {', '.join(self.supported_framerates)}")
            return
        
        framerate = parts[1]
        initial_timecode = parts[2] if len(parts) > 2 else '00:00:00:00'
        
        if framerate not in self.supported_framerates:
            print(f"Invalid framerate. Supported: {', '.join(self.supported_framerates)}")
            return
        
        # Validate timecode format
        if not re.match(r'^\d{2}:\d{2}:\d{2}:\d{2}$', initial_timecode):
            print("Invalid timecode format. Use HH:MM:SS:FF")
            return
        
        await self.send_command({
            'type': 'create_session',
            'framerate': framerate,
            'initial_timecode': initial_timecode
        })
    
    async def join_session(self, parts):
        """Join an existing session"""
        if len(parts) < 2:
            print("Usage: join <session_id>")
            return
        
        session_id = parts[1]
        await self.send_command({
            'type': 'join_session',
            'session_id': session_id
        })
    
    async def leave_session(self):
        """Leave the current session"""
        if not self.current_session:
            print("Not in a session")
            return
        
        await self.send_command({
            'type': 'leave_session'
        })
        
        self.current_session = None
        print("Left session")
    
    async def start_timecode(self):
        """Start timecode in current session"""
        if not self.current_session:
            print("Not in a session")
            return
        
        await self.send_command({
            'type': 'start_timecode'
        })
    
    async def stop_timecode(self):
        """Stop timecode in current session"""
        if not self.current_session:
            print("Not in a session")
            return
        
        await self.send_command({
            'type': 'stop_timecode'
        })
    
    async def reset_timecode(self, parts):
        """Reset timecode in current session"""
        if not self.current_session:
            print("Not in a session")
            return
        
        timecode = parts[1] if len(parts) > 1 else '00:00:00:00'
        
        # Validate timecode format
        if not re.match(r'^\d{2}:\d{2}:\d{2}:\d{2}, timecode):
            print("Invalid timecode format. Use HH:MM:SS:FF")
            return
        
        await self.send_command({
            'type': 'reset_timecode',
            'timecode': timecode
        })
    
    def show_status(self):
        """Show current client status"""
        if self.current_session:
            print(f"\nCurrent session: {self.current_session['id']}")
            print(f"Framerate: {self.current_session['framerate']} fps")
            print(f"Role: {self.current_session['role']}")
        else:
            print("\nNot in a session")
        print(f"Connected: {self.connected}")
    
    def show_help(self):
        """Show help information"""
        print("\nAvailable commands:")
        print("  create <framerate> [timecode]  - Create a new session")
        print("  join <session_id>              - Join an existing session")
        print("  leave                          - Leave current session")
        print("  start                          - Start timecode in current session")
        print("  stop                           - Stop timecode in current session")
        print("  reset [timecode]               - Reset timecode (default: 00:00:00:00)")
        print("  status                         - Show current status")
        print("  help                           - Show this help")
        print("  quit/exit                      - Disconnect and exit")
        print("\nFramerate examples: 24, 29.97, 30, 59.94, 60")
        print("Timecode format: HH:MM:SS:FF (e.g., 01:30:45:12)")
    
    def show_prompt(self):
        """Show command prompt"""
        if self.current_session:
            session_short = self.current_session['id'][:8]
            framerate = self.current_session['framerate']
            prompt = f"SMPTE[{session_short}@{framerate}fps]> "
        else:
            prompt = "SMPTE[no session]> "
        
        print(prompt, end='', flush=True)
    
    async def run(self):
        """Main client loop"""
        if not await self.connect():
            return
        
        try:
            # Start both message handler and input handler
            message_task = asyncio.create_task(self.handle_server_messages())
            input_task = asyncio.create_task(self.handle_user_input())
            
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [message_task, input_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        except KeyboardInterrupt:
            print("\nDisconnecting...")
        finally:
            await self.disconnect()


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='SMPTE Timecode Client')
    parser.add_argument('--host', default='localhost', help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, default=8080, help='Server port (default: 8080)')
    
    args = parser.parse_args()
    
    print("SMPTE Timecode Client (Python)")
    print("==============================")
    print(f"Connecting to {args.host}:{args.port}...")
    print()
    
    client = SMPTETimecodeClient(args.host, args.port)
    await client.run()


if __name__ == '__main__':
    try:
        # Check if aioconsole is available
        import aioconsole
    except ImportError:
        print("Error: aioconsole module is required")
        print("Install it with: pip install aioconsole")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"Client error: {e}")
        sys.exit(1)
