"""
Task management functionality for the CoffeeBlack SDK.

This module provides the following capabilities:
- Creating tasks
- Listening for pending tasks
- Polling for task completion
- Completing tasks with results
- Failing tasks with error messages
- Processing tasks with custom handlers
"""

import os
import time
import json
import uuid
import asyncio
import aiohttp
from typing import Dict, Any, Set, List, Optional, Callable, Union, TypeVar

# Define type variables for the task handler
T = TypeVar('T')
TaskHandler = Callable[[Dict[str, Any]], Any]

class CoffeeBlackTaskManager:
    """
    Manages tasks for the CoffeeBlack SDK.
    
    This class provides methods for creating, listening to, completing, and
    processing tasks from the CoffeeBlack API.
    """
    
    def __init__(self, 
                 api_key: str = None, 
                 base_url: str = None,
                 org_id: str = None,
                 route_id: str = None,
                 poll_interval: int = 5,
                 verbose: bool = False):
        """
        Initialize the task manager.
        
        Args:
            api_key: API key for CoffeeBlack API. If None, uses COFFEEBLACK_API_KEY env var.
            base_url: Base URL for the CoffeeBlack API. If None, uses COFFEEBLACK_API_URL env var.
            org_id: Organization ID. If None, uses COFFEEBLACK_ORG_ID env var.
            route_id: Route ID for filtering tasks. If None, uses COFFEEBLACK_ROUTE_ID env var.
            poll_interval: Interval in seconds between task polling.
            verbose: Whether to show verbose output.
        """
        # Use provided values or fall back to environment variables
        self.api_key = api_key or os.getenv("COFFEEBLACK_API_KEY")
        self.base_url = base_url or os.getenv("COFFEEBLACK_API_URL", "https://app.coffeeblack.ai")
        self.org_id = org_id or os.getenv("COFFEEBLACK_ORG_ID")
        self.route_id = route_id or os.getenv("COFFEEBLACK_ROUTE_ID")
        
        # Validate required parameters
        if not self.api_key:
            raise ValueError("API key is required. Provide it directly or set COFFEEBLACK_API_KEY environment variable.")
        if not self.org_id:
            raise ValueError("Organization ID is required. Provide it directly or set COFFEEBLACK_ORG_ID environment variable.")
            
        # Configuration
        self.poll_interval = poll_interval
        self.verbose = verbose
        self.processed_tasks: Set[str] = set()  # Track processed task IDs
        
        # Create shared HTTP session with auth headers
        self._session = None  # Will be initialized in get_session()
    
    async def get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an HTTP session with proper authentication headers.
        
        Returns:
            An aiohttp ClientSession configured with authentication headers
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            })
            
            if self.verbose:
                print(f"Created new HTTP session with API key: {self.api_key[:5]}...{self.api_key[-5:]}")
                
        return self._session
        
    async def create_task(self, 
                          input_data: Dict[str, Any], 
                          route_id: str = None, 
                          priority: int = 1,
                          conversation_id: str = None) -> Dict[str, Any]:
        """
        Create a new task in the CoffeeBlack API.
        
        Args:
            input_data: The input payload for the task
            route_id: The route ID for the task (defaults to self.route_id)
            priority: Priority level for the task (1-5, 1 is highest)
            conversation_id: Optional conversation ID to group related tasks
            
        Returns:
            Dictionary containing the created task data, including the task ID
            
        Raises:
            ValueError: If route_id is not provided and not set in the constructor
            RuntimeError: If the API request fails
        """
        # Use provided route_id or fall back to instance attribute
        route_id = route_id or self.route_id
        if not route_id:
            raise ValueError("Route ID is required. Provide it directly or set it in the constructor.")
            
        # Generate a conversation ID if not provided
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
            
        # Build request URL and payload
        url = f"{self.base_url}/api/org/{self.org_id}/tasks"
        payload = {
            "route_id": route_id,
            "input": input_data,
            "priority": priority,
            "metadata": {
                "conversation_id": conversation_id
            }
        }
        
        if self.verbose:
            print(f"Creating task with route_id: {route_id}")
            print(f"Task payload: {json.dumps(payload, indent=2)}")
            
        try:
            # Get session and make request
            session = await self.get_session()
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Failed to create task. Status: {response.status}, Error: {error_text}")
                    
                result = await response.json()
                
                if self.verbose:
                    print(f"Created task with ID: {result.get('taskId', result.get('id', 'unknown'))}")
                    
                return result
                
        except Exception as e:
            raise RuntimeError(f"Error creating task: {str(e)}")
    
    async def get_pending_tasks(self, route_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get a list of pending tasks from the CoffeeBlack API.
        
        Args:
            route_id: Optional route ID to filter tasks (defaults to self.route_id)
            limit: Maximum number of tasks to return
            
        Returns:
            List of pending task objects
            
        Raises:
            RuntimeError: If the API request fails
        """
        # Use provided route_id or fall back to instance attribute
        route_id = route_id or self.route_id
        
        # Build request URL and params
        url = f"{self.base_url}/api/org/{self.org_id}/tasks"
        params = {"limit": limit, "status": "pending"}
        
        # Add route_id to params if provided
        if route_id:
            params["route_id"] = route_id
            
        if self.verbose:
            print(f"Getting pending tasks with params: {params}")
            
        try:
            # Get session and make request
            session = await self.get_session()
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Failed to get tasks. Status: {response.status}, Error: {error_text}")
                    
                tasks = await response.json()
                
                # Filter for pending tasks (in case API doesn't filter correctly)
                pending_tasks = [task for task in tasks if task.get("status") == "pending"]
                
                if self.verbose:
                    print(f"Found {len(pending_tasks)} pending tasks")
                    if pending_tasks:
                        print(f"Task IDs: {[t.get('id') for t in pending_tasks]}")
                    
                return pending_tasks
                
        except Exception as e:
            raise RuntimeError(f"Error getting pending tasks: {str(e)}")
    
    async def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        Get details for a specific task by ID.
        
        Args:
            task_id: The ID of the task to retrieve
            
        Returns:
            Task details as a dictionary
            
        Raises:
            RuntimeError: If the API request fails
        """
        url = f"{self.base_url}/api/org/{self.org_id}/tasks/{task_id}"
        
        if self.verbose:
            print(f"Getting task details for ID: {task_id}")
            
        try:
            # Get session and make request
            session = await self.get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Failed to get task {task_id}. Status: {response.status}, Error: {error_text}")
                    
                task = await response.json()
                
                if self.verbose:
                    print(f"Task {task_id} status: {task.get('status', 'unknown')}")
                    
                return task
                
        except Exception as e:
            raise RuntimeError(f"Error getting task {task_id}: {str(e)}")
    
    async def complete_task(self, task_id: str, result: Any) -> Dict[str, Any]:
        """
        Mark a task as completed with the given result.
        
        Args:
            task_id: The ID of the task to complete
            result: The result data to attach to the task
            
        Returns:
            API response as a dictionary
            
        Raises:
            RuntimeError: If the API request fails
        """
        url = f"{self.base_url}/api/org/{self.org_id}/tasks/{task_id}/complete"
        payload = {"result": result}
        
        if self.verbose:
            print(f"Completing task {task_id}")
            
        try:
            # Get session and make request
            session = await self.get_session()
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Failed to complete task {task_id}. Status: {response.status}, Error: {error_text}")
                    
                result = await response.json()
                
                if self.verbose:
                    print(f"Task {task_id} completed successfully")
                    
                return result
                
        except Exception as e:
            raise RuntimeError(f"Error completing task {task_id}: {str(e)}")
    
    async def fail_task(self, task_id: str, error_message: str) -> Dict[str, Any]:
        """
        Mark a task as failed with the given error message.
        
        Args:
            task_id: The ID of the task to fail
            error_message: The error message to attach to the task
            
        Returns:
            API response as a dictionary
            
        Raises:
            RuntimeError: If the API request fails
        """
        url = f"{self.base_url}/api/org/{self.org_id}/tasks/{task_id}/fail"
        payload = {"error": error_message}
        
        if self.verbose:
            print(f"Failing task {task_id} with error: {error_message}")
            
        try:
            # Get session and make request
            session = await self.get_session()
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Failed to mark task {task_id} as failed. Status: {response.status}, Error: {error_text}")
                    
                result = await response.json()
                
                if self.verbose:
                    print(f"Task {task_id} marked as failed")
                    
                return result
                
        except Exception as e:
            raise RuntimeError(f"Error failing task {task_id}: {str(e)}")
    
    async def poll_task(self, 
                         task_id: str, 
                         timeout: int = 300, 
                         poll_interval: int = None) -> Optional[Dict[str, Any]]:
        """
        Poll for task completion with timeout.
        
        Args:
            task_id: The ID of the task to poll
            timeout: Maximum time in seconds to wait for completion
            poll_interval: Interval in seconds between polls (defaults to self.poll_interval)
            
        Returns:
            The task output if completed successfully, None if failed or timed out
            
        Raises:
            RuntimeError: If there's an error polling the task
        """
        poll_interval = poll_interval or self.poll_interval
        start_time = time.time()
        
        if self.verbose:
            print(f"Polling for task {task_id} completion (timeout: {timeout}s, interval: {poll_interval}s)")
            
        while (time.time() - start_time) < timeout:
            try:
                task_data = await self.get_task(task_id)
                status = task_data.get("status")
                
                if status == "completed":
                    if self.verbose:
                        print(f"Task {task_id} completed")
                    return task_data.get("output")
                elif status == "failed":
                    if self.verbose:
                        print(f"Task {task_id} failed: {task_data.get('error')}")
                    return None
                
                # Task is still pending or in progress
                if self.verbose:
                    print(f"Task {task_id} status: {status}. Checking again in {poll_interval} seconds...")
                    
                await asyncio.sleep(poll_interval)
                
            except Exception as e:
                if self.verbose:
                    print(f"Error polling task {task_id}: {str(e)}")
                await asyncio.sleep(poll_interval)
        
        if self.verbose:
            print(f"Timeout waiting for task {task_id}")
            
        return None
    
    async def process_task(self, task: Dict[str, Any], handler: TaskHandler) -> None:
        """
        Process a single task using the provided handler function.
        
        Args:
            task: The task object to process
            handler: Function that takes a task and returns a result
            
        Raises:
            RuntimeError: If there's an error processing the task
        """
        task_id = task.get("id")
        
        if not task_id:
            raise ValueError("Task object must have an 'id' field")
            
        # Skip if we've already processed this task
        if task_id in self.processed_tasks:
            if self.verbose:
                print(f"Skipping already processed task {task_id}")
            return
            
        # Mark as being processed
        self.processed_tasks.add(task_id)
        
        if self.verbose:
            print(f"Processing task {task_id}")
            
        try:
            # Extract input payload
            input_payload = task.get("input_payload") or task.get("input") or {}
            
            # If input_payload is a string, try to parse it as JSON
            if isinstance(input_payload, str):
                try:
                    input_payload = json.loads(input_payload)
                except json.JSONDecodeError:
                    if self.verbose:
                        print(f"Warning: Could not parse input_payload as JSON")
            
            # Process the task with the handler
            result = handler(input_payload)
            
            # Complete the task with the result
            await self.complete_task(task_id, result)
            
            if self.verbose:
                print(f"Task {task_id} processing completed successfully")
                
        except Exception as e:
            # If there's an error, fail the task
            error_message = str(e)
            await self.fail_task(task_id, error_message)
            
            if self.verbose:
                print(f"Task {task_id} processing failed: {error_message}")
            
            # Re-raise the exception
            raise
    
    async def listen_for_tasks(self, 
                               handler: TaskHandler,
                               route_id: str = None,
                               max_iterations: Optional[int] = None,
                               stop_on_error: bool = False) -> None:
        """
        Listen for and process pending tasks in a loop.
        
        Args:
            handler: Function that takes a task and returns a result
            route_id: Optional route ID to filter tasks (defaults to self.route_id)
            max_iterations: Optional maximum number of iterations to run
            stop_on_error: Whether to stop on task processing errors
            
        Raises:
            RuntimeError: If there's an error in the task processing loop
        """
        # Use provided route_id or fall back to instance attribute
        route_id = route_id or self.route_id
        iteration = 0
        
        if self.verbose:
            print(f"Starting task listener" + (f" for route {route_id}" if route_id else ""))
            print(f"Will run {'indefinitely' if max_iterations is None else f'for {max_iterations} iterations'}")
        
        while max_iterations is None or iteration < max_iterations:
            iteration += 1
            
            try:
                # Get pending tasks
                tasks = await self.get_pending_tasks(route_id=route_id)
                
                if not tasks:
                    if self.verbose:
                        print(f"No pending tasks found. Waiting {self.poll_interval} seconds...")
                    await asyncio.sleep(self.poll_interval)
                    continue
                
                # Process each task
                for task in tasks:
                    try:
                        await self.process_task(task, handler)
                    except Exception as e:
                        if self.verbose:
                            print(f"Error processing task: {str(e)}")
                        if stop_on_error:
                            raise
                
                # Sleep before next poll
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                if self.verbose:
                    print(f"Error in task listener loop: {str(e)}")
                if stop_on_error:
                    raise
                await asyncio.sleep(self.poll_interval)
                
        if self.verbose and max_iterations is not None:
            print(f"Task listener completed {max_iterations} iterations")
    
    async def create_ping_pong_task(self, 
                                    count: int, 
                                    conversation_id: str = None,
                                    route_id: str = None) -> str:
        """
        Create a ping-pong task for testing purposes.
        
        Args:
            count: The ping-pong counter value
            conversation_id: Optional conversation ID
            route_id: Optional route ID
            
        Returns:
            The created task ID
            
        Raises:
            RuntimeError: If there's an error creating the task
        """
        # Generate conversation ID if not provided
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())[:8]
            
        # Use provided route_id or fall back to instance attribute
        route_id = route_id or self.route_id
        if not route_id:
            raise ValueError("Route ID is required. Provide it directly or set it in the constructor.")
            
        # Create ping-pong payload
        payload = {
            "ping_pong": {
                "message": f"Ping from task creator #{count}",
                "count": count,
                "timestamp": time.time(),
                "conversation_id": conversation_id
            }
        }
        
        if self.verbose:
            print(f"Creating ping-pong task #{count} with conversation_id: {conversation_id}")
            
        # Create the task
        task_data = await self.create_task(
            input_data=payload,
            route_id=route_id,
            priority=1,
            conversation_id=conversation_id
        )
        
        # Extract task ID from response
        task_id = task_data.get("taskId") or task_data.get("id")
        
        if not task_id:
            raise RuntimeError(f"Failed to get task ID from response: {task_data}")
            
        if self.verbose:
            print(f"Created ping-pong task {task_id}")
            
        return task_id
    
    async def run_ping_pong_test(self, 
                                 max_ping_pongs: int = 3, 
                                 timeout: int = 300,
                                 route_id: str = None) -> bool:
        """
        Run a ping-pong test to verify task processing.
        
        Creates a series of ping-pong tasks and waits for responses
        to verify the task processing system is working correctly.
        
        Args:
            max_ping_pongs: Maximum number of ping-pong exchanges
            timeout: Timeout in seconds for each task
            route_id: Optional route ID
            
        Returns:
            True if all ping-pongs completed successfully, False otherwise
            
        Raises:
            RuntimeError: If there's an error in the ping-pong test
        """
        # Use provided route_id or fall back to instance attribute
        route_id = route_id or self.route_id
        if not route_id:
            raise ValueError("Route ID is required. Provide it directly or set it in the constructor.")
            
        # Generate a unique conversation ID for this test
        conversation_id = str(uuid.uuid4())[:8]
        ping_pong_count = 0
        
        if self.verbose:
            print(f"Starting ping-pong test with conversation_id: {conversation_id}")
            print(f"Will perform {max_ping_pongs} ping-pong cycles with timeout {timeout}s per task")
            
        try:
            # Initial ping
            current_task_id = await self.create_ping_pong_task(
                count=ping_pong_count,
                conversation_id=conversation_id,
                route_id=route_id
            )
            
            # Continue until max_ping_pongs reached
            while ping_pong_count < max_ping_pongs:
                # Wait for response
                result = await self.poll_task(current_task_id, timeout)
                
                if not result:
                    if self.verbose:
                        print("Failed to get task result. Breaking cycle.")
                    return False
                
                # Extract ping-pong data
                if isinstance(result, dict) and "ping_pong" in result:
                    ping_pong_data = result["ping_pong"]
                    received_count = ping_pong_data.get("count", 0)
                    message = ping_pong_data.get("message", "No message")
                    
                    if self.verbose:
                        print(f"Received response: {message}")
                    
                    # Check if we should continue
                    ping_pong_count += 1
                    if ping_pong_count >= max_ping_pongs:
                        if self.verbose:
                            print(f"Completed {ping_pong_count} ping-pongs. Ending.")
                        return True
                    
                    # Create next ping task
                    current_task_id = await self.create_ping_pong_task(
                        count=ping_pong_count,
                        conversation_id=conversation_id,
                        route_id=route_id
                    )
                else:
                    if self.verbose:
                        print("Received unexpected response format. Breaking cycle.")
                    return False
            
            return True
            
        except Exception as e:
            if self.verbose:
                print(f"Error in ping-pong test: {str(e)}")
            return False
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            if self.verbose:
                print("Closed HTTP session")


# Add a task manager class to the CoffeeBlack SDK
class TaskManager:
    """
    Task management extension for the CoffeeBlack SDK.
    
    This class is meant to be used as part of the CoffeeBlackSDK class
    and provides methods for working with tasks in the CoffeeBlack API.
    """
    
    def __init__(self, parent_sdk):
        """
        Initialize the task manager with a reference to the parent SDK.
        
        Args:
            parent_sdk: The parent CoffeeBlackSDK instance
        """
        self.sdk = parent_sdk
        self._task_manager = None
    
    def _get_task_manager(self) -> CoffeeBlackTaskManager:
        """
        Get or create a CoffeeBlackTaskManager instance.
        
        Returns:
            A CoffeeBlackTaskManager instance
        """
        if self._task_manager is None:
            self._task_manager = CoffeeBlackTaskManager(
                api_key=self.sdk.api_key,
                base_url=self.sdk.base_url,
                verbose=self.sdk.verbose
            )
        return self._task_manager
    
    async def create_task(self, 
                          org_id: str,
                          route_id: str, 
                          input_data: Dict[str, Any],
                          priority: int = 1) -> Dict[str, Any]:
        """
        Create a new task in the CoffeeBlack API.
        
        Args:
            org_id: The organization ID
            route_id: The route ID for the task
            input_data: The input payload for the task
            priority: Priority level for the task (1-5, 1 is highest)
            
        Returns:
            Dictionary containing the created task data, including the task ID
        """
        task_manager = self._get_task_manager()
        task_manager.org_id = org_id
        return await task_manager.create_task(
            input_data=input_data,
            route_id=route_id,
            priority=priority
        )
    
    async def get_pending_tasks(self, org_id: str, route_id: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get a list of pending tasks from the CoffeeBlack API.
        
        Args:
            org_id: The organization ID
            route_id: Optional route ID to filter tasks
            limit: Maximum number of tasks to return
            
        Returns:
            List of pending task objects
        """
        task_manager = self._get_task_manager()
        task_manager.org_id = org_id
        return await task_manager.get_pending_tasks(route_id=route_id, limit=limit)
    
    async def get_task(self, org_id: str, task_id: str) -> Dict[str, Any]:
        """
        Get details for a specific task by ID.
        
        Args:
            org_id: The organization ID
            task_id: The ID of the task to retrieve
            
        Returns:
            Task details as a dictionary
        """
        task_manager = self._get_task_manager()
        task_manager.org_id = org_id
        return await task_manager.get_task(task_id)
    
    async def complete_task(self, org_id: str, task_id: str, result: Any) -> Dict[str, Any]:
        """
        Mark a task as completed with the given result.
        
        Args:
            org_id: The organization ID
            task_id: The ID of the task to complete
            result: The result data to attach to the task
            
        Returns:
            API response as a dictionary
        """
        task_manager = self._get_task_manager()
        task_manager.org_id = org_id
        return await task_manager.complete_task(task_id, result)
    
    async def fail_task(self, org_id: str, task_id: str, error_message: str) -> Dict[str, Any]:
        """
        Mark a task as failed with the given error message.
        
        Args:
            org_id: The organization ID
            task_id: The ID of the task to fail
            error_message: The error message to attach to the task
            
        Returns:
            API response as a dictionary
        """
        task_manager = self._get_task_manager()
        task_manager.org_id = org_id
        return await task_manager.fail_task(task_id, error_message)
    
    async def poll_task(self, org_id: str, task_id: str, timeout: int = 300) -> Optional[Dict[str, Any]]:
        """
        Poll for task completion with timeout.
        
        Args:
            org_id: The organization ID
            task_id: The ID of the task to poll
            timeout: Maximum time in seconds to wait for completion
            
        Returns:
            The task output if completed successfully, None if failed or timed out
        """
        task_manager = self._get_task_manager()
        task_manager.org_id = org_id
        return await task_manager.poll_task(task_id, timeout)
    
    async def listen_for_tasks(self, 
                               org_id: str,
                               handler: TaskHandler,
                               route_id: str = None,
                               max_iterations: Optional[int] = None) -> None:
        """
        Listen for and process pending tasks in a loop.
        
        Args:
            org_id: The organization ID
            handler: Function that takes a task and returns a result
            route_id: Optional route ID to filter tasks
            max_iterations: Optional maximum number of iterations to run
        """
        task_manager = self._get_task_manager()
        task_manager.org_id = org_id
        await task_manager.listen_for_tasks(
            handler=handler,
            route_id=route_id,
            max_iterations=max_iterations
        )
    
    async def run_ping_pong_test(self, 
                                 org_id: str,
                                 route_id: str,
                                 max_ping_pongs: int = 3,
                                 timeout: int = 300) -> bool:
        """
        Run a ping-pong test to verify task processing.
        
        Args:
            org_id: The organization ID
            route_id: The route ID for the tasks
            max_ping_pongs: Maximum number of ping-pong exchanges
            timeout: Timeout in seconds for each task
            
        Returns:
            True if all ping-pongs completed successfully, False otherwise
        """
        task_manager = self._get_task_manager()
        task_manager.org_id = org_id
        return await task_manager.run_ping_pong_test(
            max_ping_pongs=max_ping_pongs,
            timeout=timeout,
            route_id=route_id
        )
    
    async def close(self):
        """Close the task manager session."""
        if self._task_manager:
            await self._task_manager.close() 