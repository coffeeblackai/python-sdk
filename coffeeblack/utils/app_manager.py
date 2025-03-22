"""
App management utilities for the CoffeeBlack SDK
"""

import os
import platform
import subprocess
from typing import Dict, List, Optional, Tuple, Any
import json
import shutil
from pathlib import Path
import logging
import warnings

# Set environment variable to disable tokenizers parallelism warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Configure module-level logging
logger = logging.getLogger(__name__)

# Try to import sentence-transformers for embeddings
try:
    # Suppress verbose output from transformers libraries
    logging.getLogger('sentence_transformers').setLevel(logging.WARNING)
    logging.getLogger('transformers').setLevel(logging.WARNING)
    
    # Import after logging configuration
    from sentence_transformers import SentenceTransformer, util
    import torch
    
    # Filter warnings
    warnings.filterwarnings("ignore", category=UserWarning)
    
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning("sentence-transformers not available. Semantic search will fall back to basic matching.")


class AppInfo:
    """Information about an installed application"""
    
    def __init__(self, name: str, path: str, description: Optional[str] = None, category: Optional[str] = None):
        """
        Initialize app information
        
        Args:
            name: Name of the application
            path: Full path to the executable or app bundle
            description: Optional description of the app
            category: Optional category (e.g., "browser", "editor")
        """
        self.name = name
        self.path = path
        self.description = description or name
        self.category = category
        self.embedding = None
    
    def __str__(self) -> str:
        return f"{self.name} ({self.path})"
    
    def __repr__(self) -> str:
        return f"AppInfo(name='{self.name}', path='{self.path}', category='{self.category}')"


class AppManager:
    """
    Manager for finding and launching applications using semantic search
    """
    
    def __init__(self, use_embeddings: bool = True, model_name: str = "all-MiniLM-L6-v2", verbose: bool = False):
        """
        Initialize the app manager
        
        Args:
            use_embeddings: Whether to use embeddings for semantic search
            model_name: Sentence-transformers model to use for embeddings
            verbose: Whether to show verbose output
        """
        self.use_embeddings = use_embeddings and EMBEDDINGS_AVAILABLE
        self.apps: Dict[str, AppInfo] = {}
        self.model = None
        self.system = platform.system()
        self.verbose = verbose
        
        # Set logging level based on verbosity
        if not verbose:
            logging.getLogger('sentence_transformers').setLevel(logging.ERROR)
            logging.getLogger('transformers').setLevel(logging.ERROR)
            logging.getLogger('huggingface').setLevel(logging.ERROR)
        
        # Load semantic model if available and requested
        if self.use_embeddings:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self.model = SentenceTransformer(model_name)
                    
                if self.verbose:
                    logger.info(f"Loaded sentence-transformers model: {model_name}")
            except Exception as e:
                logger.error(f"Failed to load sentence-transformers model: {e}")
                self.use_embeddings = False
        
        # Scan for installed apps
        self.refresh_app_list()
    
    def refresh_app_list(self) -> None:
        """
        Refresh the list of installed applications
        """
        self.apps.clear()
        
        if self.system == "Darwin":  # macOS
            self._scan_macos_apps()
        elif self.system == "Windows":
            self._scan_windows_apps()
        elif self.system == "Linux":
            self._scan_linux_apps()
        
        # Generate embeddings for all apps if model is available
        if self.use_embeddings and self.model:
            self._generate_embeddings()
            
        if self.verbose:
            logger.info(f"Found {len(self.apps)} applications")
        else:
            logger.debug(f"Found {len(self.apps)} applications")
    
    def _scan_macos_apps(self) -> None:
        """
        Scan for applications on macOS
        """
        # Check the main Applications folders
        application_paths = ["/Applications", "/System/Applications"]
        for applications_path in application_paths:
            if os.path.exists(applications_path):
                for item in os.listdir(applications_path):
                    if item.endswith(".app"):
                        app_path = os.path.join(applications_path, item)
                        app_name = item.replace(".app", "")
                        
                        # Try to get more info from Info.plist
                        plist_path = os.path.join(app_path, "Contents", "Info.plist")
                        category = None
                        description = None
                        
                        if os.path.exists(plist_path):
                            try:
                                # Use plutil to convert to JSON (macOS-specific)
                                result = subprocess.run(
                                    ["plutil", "-convert", "json", "-o", "-", plist_path],
                                    capture_output=True,
                                    text=True
                                )
                                if result.returncode == 0:
                                    plist_data = json.loads(result.stdout)
                                    category = plist_data.get("LSApplicationCategoryType", "").replace("public.", "")
                                    description = plist_data.get("CFBundleGetInfoString", app_name)
                            except Exception as e:
                                logger.debug(f"Error reading Info.plist for {app_name}: {e}")
                        
                        self.apps[app_name.lower()] = AppInfo(
                            name=app_name,
                            path=app_path,
                            description=description or app_name,
                            category=category
                        )
        
        # Also check user applications folder
        user_applications = os.path.expanduser("~/Applications")
        if os.path.exists(user_applications):
            for item in os.listdir(user_applications):
                if item.endswith(".app"):
                    app_path = os.path.join(user_applications, item)
                    app_name = item.replace(".app", "")
                    if app_name.lower() not in self.apps:
                        self.apps[app_name.lower()] = AppInfo(
                            name=app_name,
                            path=app_path,
                            description=app_name
                        )
    
    def _scan_windows_apps(self) -> None:
        """
        Scan for applications on Windows
        """
        # Check Program Files
        program_files = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        ]
        
        for folder in program_files:
            if os.path.exists(folder):
                for item in os.listdir(folder):
                    app_path = os.path.join(folder, item)
                    if os.path.isdir(app_path):
                        # Look for .exe files
                        exe_files = list(Path(app_path).glob("**/*.exe"))
                        if exe_files:
                            # Use the first .exe file
                            exe_path = str(exe_files[0])
                            app_name = item
                            self.apps[app_name.lower()] = AppInfo(
                                name=app_name,
                                path=exe_path,
                                description=app_name
                            )
        
        # Windows: Can also use the registry for a more complete list
        # This would require the winreg module, but we'll keep it simpler for now
    
    def _scan_linux_apps(self) -> None:
        """
        Scan for applications on Linux
        """
        # Check common application directories for .desktop files
        app_dirs = [
            "/usr/share/applications",
            "/usr/local/share/applications",
            os.path.expanduser("~/.local/share/applications")
        ]
        
        for app_dir in app_dirs:
            if os.path.exists(app_dir):
                for file in os.listdir(app_dir):
                    if file.endswith(".desktop"):
                        desktop_path = os.path.join(app_dir, file)
                        try:
                            app_name = file.replace(".desktop", "")
                            path = None
                            category = None
                            description = None
                            
                            # Parse .desktop file
                            with open(desktop_path, "r", encoding="utf-8") as f:
                                for line in f:
                                    if line.startswith("Exec="):
                                        path = line.split("=", 1)[1].strip()
                                        # Remove arguments
                                        path = path.split(" ")[0]
                                    elif line.startswith("Name="):
                                        app_name = line.split("=", 1)[1].strip()
                                    elif line.startswith("Categories="):
                                        category = line.split("=", 1)[1].strip()
                                    elif line.startswith("Comment="):
                                        description = line.split("=", 1)[1].strip()
                            
                            if path:
                                self.apps[app_name.lower()] = AppInfo(
                                    name=app_name,
                                    path=path,
                                    description=description or app_name,
                                    category=category
                                )
                        except Exception as e:
                            logger.debug(f"Error parsing .desktop file {file}: {e}")
    
    def _generate_embeddings(self) -> None:
        """
        Generate embeddings for all apps using the sentence transformer model
        """
        if not self.model:
            return
        
        app_texts = []
        for app_name, app_info in self.apps.items():
            # Create a rich text representation for the app
            text = f"{app_info.name}"
            if app_info.description and app_info.description != app_info.name:
                text += f" - {app_info.description}"
            if app_info.category:
                text += f" ({app_info.category})"
            app_texts.append(text)
        
        # Generate embeddings in a batch for efficiency
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                
                # Suppress output during embedding generation
                log_level = logging.getLogger().level
                if not self.verbose:
                    logging.getLogger().setLevel(logging.ERROR)
                
                embeddings = self.model.encode(app_texts, convert_to_tensor=True, show_progress_bar=self.verbose)
                
                # Restore log level
                logging.getLogger().setLevel(log_level)
                
            # Assign embeddings back to the app info objects
            for i, (app_name, app_info) in enumerate(self.apps.items()):
                app_info.embedding = embeddings[i]
        except Exception as e:
            logger.warning(f"Error generating embeddings: {e}")
    
    def find_app(self, query: str, threshold: float = 0.3, path: Optional[str] = None) -> List[Tuple[AppInfo, float]]:
        """
        Find applications matching the query using semantic search or basic matching
        
        Args:
            query: Natural language query (e.g., "web browser", "Safari", "text editor")
            threshold: Similarity threshold (0-1) for semantic search matches
            path: Optional direct path to an application. If provided, this takes precedence over query.
            
        Returns:
            List of tuples (AppInfo, score) sorted by relevance
        """
        # If a direct path is provided, use it
        if path:
            normalized_path = path.replace('\\ ', ' ')
            if os.path.exists(normalized_path) and ((normalized_path.endswith('.app') and self.system == "Darwin") or 
                                                 (normalized_path.endswith('.exe') and self.system == "Windows")):
                app_name = os.path.basename(normalized_path).replace('.app', '').replace('.exe', '')
                if app_name.lower() not in self.apps:
                    self._register_app_from_path(normalized_path)
                
                if app_name.lower() in self.apps:
                    return [(self.apps[app_name.lower()], 1.0)]
        
        # Handle path detection in query - normalizing the path
        normalized_query = query
        
        # If the query contains escaped spaces, normalize it
        if '\\' in query:
            normalized_query = query.replace('\\ ', ' ')
        
        # Check if the query is an actual path to an application
        path_exists = os.path.exists(normalized_query)
        is_app = (self.system == "Darwin" and normalized_query.endswith('.app')) or \
                (self.system == "Windows" and normalized_query.endswith('.exe'))
        
        if path_exists and is_app:
            # Register this app if it's not already in our list
            app_name = os.path.basename(normalized_query).replace('.app', '').replace('.exe', '')
            if app_name.lower() not in self.apps:
                self._register_app_from_path(normalized_query)
            
            # Return it with a perfect score
            if app_name.lower() in self.apps:
                return [(self.apps[app_name.lower()], 1.0)]
        
        # First, try exact matching by name
        query_lower = query.lower()
        if query_lower in self.apps:
            return [(self.apps[query_lower], 1.0)]
        
        # If embeddings are available, use semantic search
        if self.use_embeddings and self.model:
            # Encode the query
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    query_embedding = self.model.encode(query, convert_to_tensor=True, show_progress_bar=False)
                
                # Find the most similar apps
                results = []
                for app_name, app_info in self.apps.items():
                    if app_info.embedding is not None:
                        similarity = util.pytorch_cos_sim(query_embedding, app_info.embedding).item()
                        if similarity >= threshold:
                            results.append((app_info, similarity))
                
                # Sort by similarity (highest first)
                results.sort(key=lambda x: x[1], reverse=True)
                return results
            except Exception as e:
                logger.warning(f"Error in semantic search: {e}")
                # Fall back to basic matching
        
        # Fallback to basic matching if embeddings are not available
        results = []
        for app_name, app_info in self.apps.items():
            # Check if query terms appear in the app name or description
            query_terms = query_lower.split()
            matches = 0
            for term in query_terms:
                if term in app_name or (app_info.description and term in app_info.description.lower()):
                    matches += 1
            
            if matches > 0:
                score = matches / len(query_terms)
                if score >= threshold:
                    results.append((app_info, score))
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    def _register_app_from_path(self, app_path: str) -> AppInfo:
        """
        Register an application from its full path
        
        Args:
            app_path: Full path to the application
            
        Returns:
            The AppInfo object for the registered app
        """
        if not os.path.exists(app_path):
            raise FileNotFoundError(f"App path does not exist: {app_path}")
        
        if self.system == "Darwin" and app_path.endswith('.app'):
            app_name = os.path.basename(app_path).replace('.app', '')
            
            # Try to get more info from Info.plist
            plist_path = os.path.join(app_path, "Contents", "Info.plist")
            category = None
            description = None
            
            if os.path.exists(plist_path):
                try:
                    # Use plutil to convert to JSON (macOS-specific)
                    result = subprocess.run(
                        ["plutil", "-convert", "json", "-o", "-", plist_path],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        plist_data = json.loads(result.stdout)
                        category = plist_data.get("LSApplicationCategoryType", "").replace("public.", "")
                        description = plist_data.get("CFBundleGetInfoString", app_name)
                except Exception as e:
                    logger.debug(f"Error reading Info.plist for {app_name}: {e}")
            
        elif self.system == "Windows" and app_path.endswith('.exe'):
            app_name = os.path.basename(app_path).replace('.exe', '')
            description = app_name
            category = None
            
        elif self.system == "Linux":
            app_name = os.path.basename(app_path)
            description = app_name
            category = None
            
        else:
            app_name = os.path.basename(app_path)
            description = app_name
            category = None
        
        app_info = AppInfo(
            name=app_name,
            path=app_path,
            description=description or app_name,
            category=category
        )
        
        # Add to our apps dictionary
        self.apps[app_name.lower()] = app_info
        
        # If we're using embeddings, generate embedding for this app
        if self.use_embeddings and self.model:
            text = f"{app_info.name}"
            if app_info.description and app_info.description != app_info.name:
                text += f" - {app_info.description}"
            if app_info.category:
                text += f" ({app_info.category})"
            
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    app_info.embedding = self.model.encode(text, convert_to_tensor=True, show_progress_bar=False)
            except Exception as e:
                logger.debug(f"Error generating embedding for {app_name}: {e}")
        
        return app_info
    
    def open_app(self, query: str, path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Find and open an application using natural language or direct path
        
        Args:
            query: Natural language query (e.g., "open Safari", "launch Chrome")
            path: Optional direct path to an application. If provided, this takes precedence over query.
            
        Returns:
            Tuple of (success, message)
        """
        # Clean the query by removing common prefixes like "open" or "launch"
        clean_query = query.lower()
        for prefix in ["open ", "launch ", "start ", "run "]:
            if clean_query.startswith(prefix):
                clean_query = clean_query[len(prefix):]
                break
        
        # Find matching apps, prioritizing path if provided
        matching_apps = self.find_app(clean_query, path=path)
        
        if not matching_apps:
            return False, f"Could not find any application matching '{clean_query}'"
        
        # Get the best match
        best_match, score = matching_apps[0]
        
        # Try to open the application
        try:
            if self.system == "Darwin":  # macOS
                subprocess.Popen(["open", best_match.path])
            elif self.system == "Windows":
                subprocess.Popen([best_match.path])
            elif self.system == "Linux":
                subprocess.Popen([best_match.path])
            
            return True, f"Opened {best_match.name} (match score: {score:.2f})"
        except Exception as e:
            return False, f"Error opening {best_match.name}: {str(e)}"
    
    def get_app_info(self, app_name: str, path: Optional[str] = None) -> Optional[AppInfo]:
        """
        Get information about a specific application
        
        Args:
            app_name: Name of the application
            path: Optional direct path to an application. If provided, this takes precedence.
            
        Returns:
            AppInfo object or None if not found
        """
        # If a direct path is provided, try to find or register the app
        if path:
            matches = self.find_app("", path=path)
            if matches:
                return matches[0][0]
        
        app_name_lower = app_name.lower()
        
        # Try exact match first
        if app_name_lower in self.apps:
            return self.apps[app_name_lower]
        
        # Otherwise, try to find the best match
        matches = self.find_app(app_name)
        return matches[0][0] if matches else None
    
    def is_app_installed(self, app_name: str, path: Optional[str] = None) -> bool:
        """
        Check if an application is installed
        
        Args:
            app_name: Name of the application
            path: Optional direct path to an application
            
        Returns:
            True if installed, False otherwise
        """
        return self.get_app_info(app_name, path=path) is not None
    
    def get_all_apps(self) -> List[AppInfo]:
        """
        Get a list of all detected applications
        
        Returns:
            List of AppInfo objects
        """
        return list(self.apps.values()) 