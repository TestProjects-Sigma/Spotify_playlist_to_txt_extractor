import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
import requests
import base64
import configparser
import os
import threading
from pathlib import Path
from typing import Optional, Callable

class SpotifyPlaylistExtractor:
    """
    Handles Spotify playlist extraction
    """
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        """
        Initialize Spotify Playlist Extractor
        
        Args:
            client_id (str, optional): Spotify API Client ID
            client_secret (str, optional): Spotify API Client Secret
        """
        # Spotify API credentials
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""
        self.token = None
        self.is_extracting = False
        
        # Configuration file path
        self.config_file = os.path.join(str(Path.home()), ".spotify_extractor_config.ini")
        
        # Load credentials if available and not provided
        if not (client_id and client_secret):
            self.load_credentials()
    
    def load_credentials(self):
        """Load credentials from config file if it exists"""
        try:
            if os.path.exists(self.config_file):
                config = configparser.ConfigParser()
                config.read(self.config_file)
                if 'Spotify' in config:
                    self.client_id = self.client_id or config['Spotify'].get('client_id', '')
                    self.client_secret = self.client_secret or config['Spotify'].get('client_secret', '')
        except Exception:
            # If there's any error reading the config, just use empty credentials
            pass
    
    def save_credentials(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        """
        Save credentials to config file
        
        Args:
            client_id (str, optional): Spotify API Client ID
            client_secret (str, optional): Spotify API Client Secret
        
        Returns:
            bool: True if save successful, False otherwise
        """
        try:
            # Use provided credentials or existing ones
            save_client_id = client_id or self.client_id
            save_client_secret = client_secret or self.client_secret
            
            config = configparser.ConfigParser()
            config['Spotify'] = {
                'client_id': save_client_id,
                'client_secret': save_client_secret
            }
            with open(self.config_file, 'w') as f:
                config.write(f)
            return True
        except Exception:
            return False
    
    def authenticate(self):
        """
        Get Spotify API access token
        
        Returns:
            Tuple of (success, message)
        """
        # Validate credentials
        if not self.client_id or not self.client_secret:
            return False, "Missing Spotify API credentials"
        
        auth_url = "https://accounts.spotify.com/api/token"
        auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {"grant_type": "client_credentials"}
        
        try:
            response = requests.post(auth_url, headers=headers, data=data)
            response.raise_for_status()
            self.token = response.json()["access_token"]
            return True, "Authentication successful"
        except requests.exceptions.RequestException as e:
            return False, f"Authentication error: {str(e)}"
    
    def extract_playlist_id(self, playlist_url: str) -> Optional[str]:
        """
        Extract playlist ID from Spotify URL
        
        Args:
            playlist_url (str): Spotify playlist URL
        
        Returns:
            str or None: Extracted playlist ID
        """
        pattern = r'spotify\.com/playlist/([a-zA-Z0-9]+)'
        match = re.search(pattern, playlist_url)
        return match.group(1) if match else None
    
    def get_playlist_tracks(self, playlist_id: str, callback: Optional[Callable] = None):
        """
        Get all tracks from a playlist
        
        Args:
            playlist_id (str): Spotify playlist ID
            callback (callable, optional): Progress callback function
        
        Returns:
            List of track dictionaries
        """
        # Authenticate if no token
        if not self.token:
            success, message = self.authenticate()
            if not success:
                if callback:
                    callback(False, message)
                return []
        
        tracks = []
        next_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            while next_url and self.is_extracting:
                response = requests.get(next_url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                for item in data["items"]:
                    if item.get("track"):
                        track_name = item["track"]["name"]
                        artists = ", ".join([artist["name"] for artist in item["track"]["artists"]])
                        tracks.append({"track": track_name, "artists": artists})
                
                # Update progress if callback provided
                if callback:
                    callback(True, f"Retrieved {len(tracks)} tracks so far...")
                
                # Get next page of results
                next_url = data.get("next")
            
            return tracks
        except requests.exceptions.RequestException as e:
            if callback:
                callback(False, f"Error fetching tracks: {str(e)}")
            return []
    
    def save_to_file(self, tracks, file_path):
        """
        Save tracks to file
        
        Args:
            tracks (List[Dict]): List of tracks
            file_path (str): Path to save file
        
        Returns:
            Tuple of (success, message)
        """
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for track in tracks:
                    f.write(f"{track['track']} - {track['artists']}\n")
            return True, f"Successfully saved {len(tracks)} tracks to {file_path}"
        except Exception as e:
            return False, f"Error saving file: {str(e)}"
    
    def extract_playlist(self, playlist_url, output_file, callback=None):
        """
        Extract playlist tracks and save to file
        
        Args:
            playlist_url (str): Spotify playlist URL
            output_file (str): Path to save output file
            callback (callable, optional): Progress callback function
        
        Returns:
            Tuple of (success, message)
        """
        self.is_extracting = True
        
        # Extract playlist ID
        playlist_id = self.extract_playlist_id(playlist_url)
        if not playlist_id:
            if callback:
                callback(False, "Invalid Spotify playlist URL")
            return False, "Invalid Spotify playlist URL"
        
        # Get tracks
        tracks = self.get_playlist_tracks(playlist_id, callback)
        
        # Stop if extraction was cancelled
        if not self.is_extracting:
            if callback:
                callback(False, "Extraction cancelled")
            return False, "Extraction cancelled"
        
        if not tracks:
            if callback:
                callback(False, "No tracks found or error occurred")
            return False, "No tracks found or error occurred"
        
        # Save to file
        return self.save_to_file(tracks, output_file)
    
    def cancel_extraction(self):
        """
        Cancel ongoing extraction
        """
        self.is_extracting = False


class SpotifyExtractorGUI:
    """
    Spotify Playlist Extractor GUI
    """
    def __init__(self, master=None):
        """
        Initialize Spotify Extractor GUI
        
        Args:
            master (tk.Tk or tk.Frame, optional): Parent window or frame
        """
        # If no master is provided, create a new Tk instance
        if master is None:
            self.root = tk.Tk()
            self.root.title("Spotify Playlist Extractor")
        else:
            self.root = master
        
        # Create extractor
        self.extractor = SpotifyPlaylistExtractor()
        
        # Setup UI
        self.setup_ui()
    
    def setup_ui(self):
        """
        Create GUI components
        """
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Playlist URL
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=(0, 10))
        
        url_label = ttk.Label(url_frame, text="Spotify Playlist URL:")
        url_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Output file selection
        file_frame = ttk.Frame(main_frame)
        file_frame.pack(fill=tk.X, pady=(0, 20))
        
        file_label = ttk.Label(file_frame, text="Output File:")
        file_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.file_entry = ttk.Entry(file_frame)
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        browse_button = ttk.Button(file_frame, text="Browse", command=self.browse_file)
        browse_button.pack(side=tk.LEFT)
        
        # Credentials frame
        cred_frame = ttk.LabelFrame(main_frame, text="Spotify API Credentials")
        cred_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Client ID
        client_id_frame = ttk.Frame(cred_frame)
        client_id_frame.pack(fill=tk.X, pady=5, padx=10)
        
        client_id_label = ttk.Label(client_id_frame, text="Client ID:")
        client_id_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.client_id_entry = ttk.Entry(client_id_frame)
        self.client_id_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Pre-fill with saved client ID if available
        if self.extractor.client_id:
            self.client_id_entry.insert(0, self.extractor.client_id)
        
        # Client Secret
        client_secret_frame = ttk.Frame(cred_frame)
        client_secret_frame.pack(fill=tk.X, pady=(0, 5), padx=10)
        
        client_secret_label = ttk.Label(client_secret_frame, text="Client Secret:")
        client_secret_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.client_secret_entry = ttk.Entry(client_secret_frame, show="*")
        self.client_secret_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Pre-fill with saved client secret if available
        if self.extractor.client_secret:
            self.client_secret_entry.insert(0, self.extractor.client_secret)
        
        # Remember credentials checkbox
        self.remember_var = tk.BooleanVar(value=True)
        remember_check = ttk.Checkbutton(
            cred_frame, 
            text="Remember these credentials", 
            variable=self.remember_var
        )
        remember_check.pack(anchor=tk.W, padx=10, pady=(0, 5))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.extract_button = ttk.Button(
            button_frame, 
            text="Extract Playlist", 
            command=self.start_extraction
        )
        self.extract_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.cancel_button = ttk.Button(
            button_frame, 
            text="Cancel", 
            command=self.cancel_extraction, 
            state=tk.DISABLED
        )
        self.cancel_button.pack(side=tk.LEFT)
        
        # Status and progress
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(
            main_frame, 
            textvariable=self.status_var, 
            wraplength=550
        )
        status_label.pack(fill=tk.X, pady=(10, 0))
        
        self.progress = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=(10, 0))
    
    def browse_file(self):
        """
        Open file dialog to choose output file
        """
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, file_path)
    
    def start_extraction(self):
        """
        Start playlist extraction in a separate thread
        """
        # Get and validate inputs
        playlist_url = self.url_entry.get().strip()
        output_file = self.file_entry.get().strip()
        client_id = self.client_id_entry.get().strip()
        client_secret = self.client_secret_entry.get().strip()
        remember_credentials = self.remember_var.get()
        
        # Validate inputs
        if not playlist_url:
            messagebox.showerror("Error", "Please enter a Spotify playlist URL")
            return
        
        if not output_file:
            messagebox.showerror("Error", "Please select an output file")
            return
        
        if not client_id or not client_secret:
            messagebox.showerror("Error", "Please enter your Spotify API credentials")
            return
        
        # Update extractor credentials
        self.extractor.client_id = client_id
        self.extractor.client_secret = client_secret
        
        # Save credentials if requested
        if remember_credentials:
            self.extractor.save_credentials()
        
        # Update UI
        self.extract_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.NORMAL)
        self.progress.start()
        self.status_var.set("Starting extraction...")
        
        # Start extraction in a separate thread
        threading.Thread(
            target=self.run_extraction, 
            args=(playlist_url, output_file), 
            daemon=True
        ).start()
    
    def run_extraction(self, playlist_url, output_file):
        """
        Run extraction process in a separate thread
        
        Args:
            playlist_url (str): Spotify playlist URL
            output_file (str): Path to save output file
        """
        success, message = self.extractor.extract_playlist(
            playlist_url, 
            output_file,
            callback=self.update_status
        )
        
        # Update UI when finished
        self.root.after(0, self.extraction_finished, success, message)
    
    def update_status(self, success, message):
        """
        Update status from extraction thread
        
        Args:
            success (bool): Whether the operation was successful
            message (str): Status message
        """
        self.root.after(0, lambda: self.status_var.set(message))
    
    def extraction_finished(self, success, message):
        """
        Called when extraction is complete
        
        Args:
            success (bool): Whether the extraction was successful
            message (str): Result message
        """
        self.progress.stop()
        self.extract_button.config(state=tk.NORMAL)
        self.cancel_button.config(state=tk.DISABLED)
        self.status_var.set(message)
        
        if success:
            messagebox.showinfo("Success", message)
        else:
            messagebox.showerror("Error", message)
    
    def cancel_extraction(self):
        """
        Cancel ongoing extraction
        """
        self.extractor.cancel_extraction()
        self.status_var.set("Cancelling extraction...")
    
    def run(self):
        """
        Start the GUI main loop if this is the main window
        """
        if isinstance(self.root, tk.Tk):
            self.root.mainloop()

# Version for standalone use
__version__ = "1.1.2"

def main():
    """
    Run the Spotify Playlist Extractor as a standalone application
    """
    app = SpotifyExtractorGUI()
    app.run()

if __name__ == "__main__":
    main()