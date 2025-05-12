import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import re
import shutil
import threading
import difflib
import logging
import configparser
import json
from pathlib import Path
from typing import List, Dict, Tuple, Set, Optional
import importlib.util
import sys
import traceback

# Version
__version__ = "1.0.0"

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger("MusicPlaylistManager")

class MusicFile:
    """Represents a music file with metadata and matching capabilities"""
    
    def __init__(self, full_path: str):
        self.full_path = full_path
        self.filename = os.path.basename(full_path)
        self.extension = os.path.splitext(full_path)[1].lower()[1:]  # Remove the dot
        self.size = os.path.getsize(full_path)
        self.artist = ""
        self.song = ""
        self.track_num = None
        
        # Parse the filename to extract artist and song
        self._parse_filename()
        
        # Get additional metadata if possible
        self.metadata = self._extract_metadata()
    
    def _parse_filename(self):
        """Parse filename to extract artist, song, and track number"""
        # Remove the extension
        name_without_ext = os.path.splitext(self.filename)[0]
        
        # Try to extract track number if present
        track_pattern = r'^(\d+)[\s_-]*'
        track_match = re.match(track_pattern, name_without_ext)
        if track_match:
            self.track_num = int(track_match.group(1))
            # Remove track number from the name
            name_without_ext = re.sub(track_pattern, '', name_without_ext)
        
        # Try different filename patterns for "Artist - Song" format
        artist_first_patterns = [
            # "Artist - Song"
            r'^(.*?)\s*-\s*(.*?)$',
            # "Artist_-_Song"
            r'^(.*?)_-_(.*?)$',
            # "Artist_Song"
            r'^(.*?)_(.*?)$'
        ]
        
        # Try different filename patterns for "Song - Artist" format
        song_first_patterns = [
            # "Song - Artist"
            r'^(.*?)\s*-\s*(.*?)$',
            # "Song_-_Artist"
            r'^(.*?)_-_(.*?)$',
            # "Song_Artist"
            r'^(.*?)_(.*?)$'
        ]
        
        # Try artist first patterns
        for pattern in artist_first_patterns:
            match = re.match(pattern, name_without_ext)
            if match:
                self.artist = match.group(1).strip()
                self.song = match.group(2).strip()
                if self.artist and self.song:  # If both parts are non-empty
                    return
        
        # If artist first patterns didn't work, try song first patterns
        for pattern in song_first_patterns:
            match = re.match(pattern, name_without_ext)
            if match:
                self.song = match.group(1).strip()
                self.artist = match.group(2).strip()
                if self.artist and self.song:  # If both parts are non-empty
                    return
        
        # If no pattern matched, use the whole filename as the song name
        if not self.artist and not self.song:
            self.song = name_without_ext
    
    def _extract_metadata(self) -> Dict:
        """Extract metadata from the music file"""
        metadata = {
            "length": "Unknown",
            "quality": "Unknown"
        }
        
        # Try to extract ID3 tags (only if necessary libraries are available)
        try:
            if self.extension in ["mp3", "flac", "ogg", "aac", "m4a"]:
                # Check if mutagen is installed
                if importlib.util.find_spec("mutagen") is not None:
                    import mutagen
                    audio = mutagen.File(self.full_path)
                    if audio:
                        # Extract duration in seconds
                        if hasattr(audio, "info") and hasattr(audio.info, "length"):
                            length_secs = audio.info.length
                            minutes = int(length_secs // 60)
                            seconds = int(length_secs % 60)
                            metadata["length"] = f"{minutes}:{seconds:02d}"
                        
                        # Extract quality
                        if hasattr(audio, "info") and hasattr(audio.info, "bitrate"):
                            metadata["quality"] = f"{audio.info.bitrate // 1000} kbps"
                        
                        # Extract tags
                        if hasattr(audio, "tags"):
                            # Use the metadata tags if available and if we couldn't parse from filename
                            if not self.artist and "artist" in audio:
                                self.artist = audio["artist"][0]
                            if not self.song and "title" in audio:
                                self.song = audio["title"][0]
        except Exception as e:
            logger.warning(f"Error extracting metadata from {self.full_path}: {str(e)}")
        
        return metadata
    
    def match_query(self, query: str, threshold: float = 0.6) -> float:
        """Match this file against a search query, return similarity score"""
        query = query.lower()
        query_parts = set(re.sub(r'[^\w\s]', ' ', query).split())
        
        # Text to match against (filename, artist, song)
        text = f"{self.filename.lower()} {self.artist.lower()} {self.song.lower()}"
        text_parts = set(re.sub(r'[^\w\s]', ' ', text).split())
        
        # Check if all query parts are in the text
        if not query_parts or not all(part in text for part in query_parts):
            return 0.0
        
        # If we're just looking for simple word matches
        if threshold <= 0.5:
            return 1.0
        
        # For higher thresholds, use fuzzy matching
        # Try to match against the full query first
        full_match_score = difflib.SequenceMatcher(None, query, text).ratio()
        
        # Then try to match artist + song combination
        artist_song = f"{self.artist.lower()} - {self.song.lower()}"
        artist_song_score = difflib.SequenceMatcher(None, query, artist_song).ratio()
        
        # Try reversed song + artist combination
        song_artist = f"{self.song.lower()} - {self.artist.lower()}"
        song_artist_score = difflib.SequenceMatcher(None, query, song_artist).ratio()
        
        # Return the best match score
        return max(full_match_score, artist_song_score, song_artist_score)

class MusicDatabase:
    """Manages scanning and searching music files"""
    
    def __init__(self):
        self.music_files: List[MusicFile] = []
        self.directories: List[str] = []
        self.file_extensions: Set[str] = {"mp3", "m4a", "flac", "ogg", "aac", "wav"}
        self.is_scanning = False
        self.scan_thread = None
        self.scan_progress_callback = None
    
    def add_directory(self, directory: str) -> bool:
        """Add a directory to the list of directories to scan"""
        if not os.path.isdir(directory):
            return False
        
        if directory not in self.directories:
            self.directories.append(directory)
            return True
        return False
    
    def remove_directory(self, directory: str) -> bool:
        """Remove a directory from the list"""
        if directory in self.directories:
            self.directories.remove(directory)
            return True
        return False
    
    def set_extensions(self, extensions: Set[str]):
        """Set the allowed file extensions"""
        self.file_extensions = extensions
    
    def scan_directories(self, progress_callback=None):
        """Scan all directories for music files with the specified extensions"""
        if self.is_scanning:
            return False
        
        self.scan_progress_callback = progress_callback
        self.is_scanning = True
        self.music_files = []
        
        self.scan_thread = threading.Thread(target=self._scan_worker)
        self.scan_thread.daemon = True
        self.scan_thread.start()
        
        return True
    
    def _scan_worker(self):
        """Worker thread for scanning directories"""
        try:
            total_files = 0
            processed_files = 0
            
            # First count total files to scan
            for directory in self.directories:
                for root, _, files in os.walk(directory):
                    for file in files:
                        ext = os.path.splitext(file)[1].lower()[1:]  # Remove the dot
                        if ext in self.file_extensions:
                            total_files += 1
            
            # Report initial progress
            if self.scan_progress_callback:
                self.scan_progress_callback(0, total_files, "Starting scan...")
            
            # Then scan and process files
            for directory in self.directories:
                for root, _, files in os.walk(directory):
                    for file in files:
                        if not self.is_scanning:
                            # Scanning was cancelled
                            if self.scan_progress_callback:
                                self.scan_progress_callback(
                                    processed_files, total_files, "Scan cancelled."
                                )
                            return
                        
                        ext = os.path.splitext(file)[1].lower()[1:]  # Remove the dot
                        if ext in self.file_extensions:
                            full_path = os.path.join(root, file)
                            try:
                                music_file = MusicFile(full_path)
                                self.music_files.append(music_file)
                            except Exception as e:
                                logger.error(f"Error processing file {full_path}: {str(e)}")
                            
                            processed_files += 1
                            if self.scan_progress_callback and total_files > 0:
                                progress = (processed_files / total_files) * 100
                                self.scan_progress_callback(
                                    processed_files, 
                                    total_files,
                                    f"Scanned {processed_files} of {total_files} files ({progress:.1f}%)"
                                )
            
            if self.scan_progress_callback:
                self.scan_progress_callback(
                    total_files, total_files, f"Scan complete. Found {len(self.music_files)} music files."
                )
        except Exception as e:
            logger.error(f"Error during scan: {str(e)}")
            if self.scan_progress_callback:
                self.scan_progress_callback(0, 0, f"Error during scan: {str(e)}")
        finally:
            self.is_scanning = False
    
    def cancel_scan(self):
        """Cancel an in-progress scan"""
        self.is_scanning = False
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(1.0)  # Wait for thread to terminate
    
    def search(self, query: str, threshold: float = 0.6) -> List[Tuple[MusicFile, float]]:
        """
        Search for music files matching the query
        
        Args:
            query: The search query
            threshold: Similarity threshold (0.0 to 1.0)
            
        Returns:
            List of (MusicFile, score) tuples sorted by score
        """
        if not query.strip():
            return []
        
        results = []
        for music_file in self.music_files:
            score = music_file.match_query(query, threshold)
            if score >= threshold:
                results.append((music_file, score))
        
        # Sort by score (descending)
        return sorted(results, key=lambda x: x[1], reverse=True)
    
    def match_playlist(self, playlist_entries: List[str], threshold: float = 0.6) -> List[Tuple[str, List[Tuple[MusicFile, float]]]]:
        """
        Match playlist entries to music files
        
        Args:
            playlist_entries: List of playlist entries (text lines)
            threshold: Similarity threshold (0.0 to 1.0)
            
        Returns:
            List of (playlist_entry, [(music_file, score), ...]) tuples
        """
        results = []
        for entry in playlist_entries:
            entry_matches = []
            for music_file in self.music_files:
                score = music_file.match_query(entry, threshold)
                if score >= threshold:
                    entry_matches.append((music_file, score))
            
            # Sort matches by score (descending) and add to results
            sorted_matches = sorted(entry_matches, key=lambda x: x[1], reverse=True)
            results.append((entry, sorted_matches))
        
        return results

class SettingsManager:
    """Manages application settings"""
    
    def __init__(self):
        self.config_dir = os.path.join(str(Path.home()), ".music_playlist_manager")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.settings = {
            "directories": [],
            "extensions": ["mp3", "m4a", "flac", "ogg", "aac", "wav"],
            "similarity_threshold": 70,  # Store as integer 1-100
            "output_directory": "",
            "last_playlist_file": ""
        }
        
        # Create config directory if it doesn't exist
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Load settings if they exist
        self.load_settings()
    
    def load_settings(self):
        """Load settings from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.settings.update(json.load(f))
        except Exception as e:
            logger.error(f"Error loading settings: {str(e)}")
    
    def save_settings(self):
        """Save settings to config file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving settings: {str(e)}")
    
    def get(self, key, default=None):
        """Get a setting value"""
        return self.settings.get(key, default)
    
    def set(self, key, value):
        """Set a setting value"""
        self.settings[key] = value
        self.save_settings()

class ConsoleTab(ttk.Frame):
    """Tab for console output"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the console UI"""
        # Create a text widget for console output
        self.console = tk.Text(self, wrap=tk.WORD, bg="black", fg="white", font=("Courier", 10))
        self.console.pack(fill=tk.BOTH, expand=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(self.console, command=self.console.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.console.config(yscrollcommand=scrollbar.set)
        
        # Make the console read-only
        self.console.config(state=tk.DISABLED)
        
        # Add handler to redirect logger output to this console
        self.log_handler = ConsoleLogHandler(self)
        logger.addHandler(self.log_handler)
    
    def log(self, message, level=logging.INFO):
        """Log a message to the console"""
        # Define colors for different log levels
        colors = {
            logging.DEBUG: "gray",
            logging.INFO: "white",
            logging.WARNING: "yellow",
            logging.ERROR: "red",
            logging.CRITICAL: "red"
        }
        
        # Get the color for this level
        color = colors.get(level, "white")
        
        # Enable editing
        self.console.config(state=tk.NORMAL)
        
        # Add timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Insert the message with color
        self.console.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.console.insert(tk.END, message + "\n", color)
        
        # Configure tags for colors
        self.console.tag_config("timestamp", foreground="cyan")
        self.console.tag_config("gray", foreground="gray")
        self.console.tag_config("white", foreground="white")
        self.console.tag_config("yellow", foreground="yellow")
        self.console.tag_config("red", foreground="red")
        
        # Scroll to the end
        self.console.see(tk.END)
        
        # Disable editing
        self.console.config(state=tk.DISABLED)

class ConsoleLogHandler(logging.Handler):
    """Log handler that redirects logging to the console tab"""
    
    def __init__(self, console_tab):
        super().__init__()
        self.console_tab = console_tab
    
    def emit(self, record):
        """Called when a log record is emitted"""
        # Format the record
        msg = self.format(record)
        
        # Schedule the message to be displayed in the GUI thread
        self.console_tab.after(0, self.console_tab.log, msg, record.levelno)

class PlaylistMatchPreview(tk.Toplevel):
    """Preview window for playlist matches"""
    
    def __init__(self, parent, playlist_matches, threshold, output_dir=None):
        super().__init__(parent)
        self.parent = parent
        self.playlist_matches = playlist_matches
        self.threshold = threshold
        self.output_dir = output_dir or os.path.join(os.getcwd(), "export")
        self.selected_files = set()
        self.total_entries = len(playlist_matches)
        self.matched_entries = sum(1 for _, matches in playlist_matches if matches)
        self.total_matches = sum(len(matches) for _, matches in playlist_matches)
        
        # Set window properties
        self.title("Playlist Match Preview")
        self.geometry("1000x600")
        self.minsize(800, 500)
        
        self.setup_ui()
        self.populate_table()
    
    def setup_ui(self):
        """Set up the preview UI"""
        # Main layout
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Summary frame at the top
        summary_frame = ttk.LabelFrame(main_frame, text="Summary", padding=10)
        summary_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Summary info
        ttk.Label(summary_frame, text=f"Total playlist entries: {self.total_entries}").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Label(summary_frame, text=f"Entries with matches: {self.matched_entries}").grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(summary_frame, text=f"Total files found: {self.total_matches}").grid(row=0, column=2, sticky=tk.W, padx=5)
        
        # Threshold adjustment frame
        threshold_frame = ttk.Frame(summary_frame)
        threshold_frame.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))
        
        ttk.Label(threshold_frame, text="Similarity Threshold:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.threshold_var = tk.IntVar(value=int(self.threshold * 100))
        threshold_scale = ttk.Scale(
            threshold_frame,
            from_=1,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.threshold_var,
            length=200
        )
        threshold_scale.pack(side=tk.LEFT, padx=(0, 5))
        
        threshold_value = ttk.Label(threshold_frame, text=f"{self.threshold_var.get()}%")
        threshold_scale.config(command=lambda val: threshold_value.config(text=f"{int(float(val))}%"))
        threshold_value.pack(side=tk.LEFT, padx=(0, 10))
        
        retry_button = ttk.Button(
            threshold_frame,
            text="Retry with New Threshold",
            command=self.retry_with_new_threshold
        )
        retry_button.pack(side=tk.LEFT)
        
        # Output directory frame
        output_frame = ttk.Frame(summary_frame)
        output_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))
        
        ttk.Label(output_frame, text="Output Directory:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.output_var = tk.StringVar(value=self.output_dir)
        output_entry = ttk.Entry(output_frame, textvariable=self.output_var, width=50)
        output_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        browse_button = ttk.Button(
            output_frame,
            text="Browse...",
            command=self.browse_output
        )
        browse_button.pack(side=tk.LEFT)
        
        # Create table frame
        table_frame = ttk.Frame(main_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create treeview for matches
        self.tree = ttk.Treeview(
            table_frame,
            columns=("Select", "Playlist Entry", "Matched File", "Match Score", "Path", "Info"),
            show="headings",
            selectmode="browse"
        )
        
        # Set up scrollbars
        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Pack scrollbars
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Configure columns
        self.tree.column("Select", width=50, anchor=tk.CENTER, stretch=False)
        self.tree.column("Playlist Entry", width=200, anchor=tk.W)
        self.tree.column("Matched File", width=200, anchor=tk.W)
        self.tree.column("Match Score", width=100, anchor=tk.CENTER, stretch=False)
        self.tree.column("Path", width=300, anchor=tk.W)
        self.tree.column("Info", width=150, anchor=tk.W)
        
        # Add headings
        self.tree.heading("Select", text="Select")
        self.tree.heading("Playlist Entry", text="Playlist Entry")
        self.tree.heading("Matched File", text="Matched File")
        self.tree.heading("Match Score", text="Match Score")
        self.tree.heading("Path", text="File Path")
        self.tree.heading("Info", text="File Info")
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X)
        
        # Buttons
        select_all_button = ttk.Button(
            buttons_frame,
            text="Select All",
            command=self.select_all
        )
        select_all_button.pack(side=tk.LEFT, padx=(0, 5))
        
        clear_button = ttk.Button(
            buttons_frame,
            text="Clear Selection",
            command=self.clear_selection
        )
        clear_button.pack(side=tk.LEFT, padx=(0, 5))
        
        copy_button = ttk.Button(
            buttons_frame,
            text="Copy Selected Files",
            command=self.copy_selected
        )
        copy_button.pack(side=tk.RIGHT, padx=(5, 0))
        
        cancel_button = ttk.Button(
            buttons_frame,
            text="Cancel",
            command=self.destroy
        )
        cancel_button.pack(side=tk.RIGHT, padx=(0, 5))
        
        # Bind checkbox toggle
        self.tree.bind("<Double-1>", self.toggle_selection)
    
    def populate_table(self):
        """Populate the table with playlist matches"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add playlist entries and matches
        for entry, matches in self.playlist_matches:
            if not matches:
                # Add entry with no matches
                self.tree.insert(
                    "",
                    tk.END,
                    values=("", entry, "<No matches found>", "", "", ""),
                    tags=("no_match",)
                )
            else:
                # Add each match for this entry
                for i, (music_file, score) in enumerate(matches):
                    # Create a unique ID for this item
                    item_id = self.tree.insert(
                        "",
                        tk.END,
                        values=(
                            "☐",  # Unchecked checkbox
                            entry if i == 0 else "",  # Only show entry for first match
                            f"{music_file.artist} - {music_file.song}" if music_file.artist and music_file.song else music_file.filename,
                            f"{score:.0%}",
                            music_file.full_path,
                            f"{music_file.metadata.get('length', '')} | {music_file.extension.upper()}"
                        ),
                        tags=("match",)
                    )
                    # Store the MusicFile object with the item
                    self.tree.item(item_id, tags=(item_id,))
        
        # Configure row appearance
        self.tree.tag_configure("no_match", background="#FFCCCC")
        
        # Adjust column widths to content
        for col in self.tree["columns"]:
            self.tree.column(col, width=tk.font.Font().measure(col) + 20)
    
    def toggle_selection(self, event):
        """Toggle selection of a row when clicked"""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            item = self.tree.identify_row(event.y)
            if item:
                values = list(self.tree.item(item, "values"))
                if values and len(values) >= 5:
                    if values[0] == "☐":  # Unchecked
                        values[0] = "☑"  # Checked
                        self.selected_files.add(values[4])  # Add path to selected
                    else:
                        values[0] = "☐"  # Unchecked
                        if values[4] in self.selected_files:
                            self.selected_files.remove(values[4])
                    
                    self.tree.item(item, values=values)
    
    def select_all(self):
        """Select all files"""
        for item in self.tree.get_children():
            values = list(self.tree.item(item, "values"))
            if values and len(values) >= 5 and values[2] != "<No matches found>":
                values[0] = "☑"  # Checked
                self.tree.item(item, values=values)
                self.selected_files.add(values[4])  # Add path to selected
    
    def clear_selection(self):
        """Clear all selections"""
        for item in self.tree.get_children():
            values = list(self.tree.item(item, "values"))
            if values and len(values) >= 5:
                values[0] = "☐"  # Unchecked
                self.tree.item(item, values=values)
        self.selected_files.clear()
    
    def browse_output(self):
        """Browse for output directory"""
        directory = filedialog.askdirectory(
            initialdir=self.output_var.get(),
            title="Select Output Directory"
        )
        if directory:
            self.output_var.set(directory)
            self.output_dir = directory
    
    def retry_with_new_threshold(self):
        """Retry matching with the new threshold"""
        new_threshold = self.threshold_var.get() / 100.0
        
        if new_threshold != self.threshold:
            # Close this window and ask parent to create a new one with the new threshold
            self.destroy()
            self.parent.retry_playlist_match(new_threshold)
    
    def copy_selected(self):
        """Copy selected files to the output directory"""
        if not self.selected_files:
            messagebox.showwarning("No Selection", "No files selected for copying.")
            return
        
        output_dir = self.output_var.get()
        if not output_dir:
            messagebox.showerror("Error", "Output directory not specified.")
            return
        
        # Create the output directory if it doesn't exist
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create output directory: {str(e)}")
            return
        
        # Start copying in a separate thread to keep the UI responsive
        threading.Thread(
            target=self._copy_worker,
            args=(list(self.selected_files), output_dir),
            daemon=True
        ).start()
    
    def _copy_worker(self, files, output_dir):
        """Worker thread for copying files"""
        try:
            # Update the UI to show we're starting
            self.after(0, lambda: logger.info(f"Starting to copy {len(files)} files to {output_dir}..."))
            
            copied = 0
            failed = 0
            
            for file_path in files:
                try:
                    filename = os.path.basename(file_path)
                    dest_path = os.path.join(output_dir, filename)
                    
                    # Check if file already exists
                    if os.path.exists(dest_path):
                        # Find a unique name with a counter
                        name, ext = os.path.splitext(filename)
                        counter = 1
                        while os.path.exists(os.path.join(output_dir, f"{name} ({counter}){ext}")):
                            counter += 1
                        dest_path = os.path.join(output_dir, f"{name} ({counter}){ext}")
                    
                    # Copy the file
                    shutil.copy2(file_path, dest_path)
                    copied += 1
                    
                    # Update progress
                    if copied % 5 == 0 or copied == len(files):
                        self.after(0, lambda c=copied, t=len(files): 
                            logger.info(f"Copied {c} of {t} files..."))
                
                except Exception as e:
                    logger.error(f"Failed to copy {file_path}: {str(e)}")
                    failed += 1
            
            # Show completion message
            self.after(0, lambda c=copied, f=failed: 
                logger.info(f"Copy complete. Successfully copied {c} files. Failed: {f}"))
            
            # Show a message box when done
            self.after(0, lambda c=copied, f=failed:
                messagebox.showinfo("Copy Complete", 
                                   f"Successfully copied {c} files to {output_dir}.\nFailed: {f}")
            )
            
        except Exception as e:
            logger.error(f"Error during copy operation: {str(e)}")
            self.after(0, lambda e=str(e):
                messagebox.showerror("Error", f"Error during copy operation: {e}")
            )

class ManualSearchTab(ttk.Frame):
    """Tab for manual searching"""
    
    def __init__(self, parent, music_db, settings_manager):
        super().__init__(parent)
        self.parent = parent
        self.music_db = music_db
        self.settings_manager = settings_manager
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI for manual search"""
        # Main layout
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Search frame
        search_frame = ttk.LabelFrame(main_frame, text="Search", padding=10)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Search field
        search_label = ttk.Label(search_frame, text="Search Query:")
        search_label.grid(row=0, column=0, padx=(0, 5), sticky=tk.W)
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.grid(row=0, column=1, padx=(0, 5), sticky=tk.EW)
        
        # Bind Enter key to search
        search_entry.bind("<Return>", lambda e: self.perform_search())
        
        # Search button
        search_button = ttk.Button(
            search_frame,
            text="Search",
            command=self.perform_search
        )
        search_button.grid(row=0, column=2, padx=(0, 5))
        
        # Threshold slider
        ttk.Label(search_frame, text="Similarity Threshold:").grid(row=1, column=0, padx=(0, 5), sticky=tk.W, pady=(10, 0))
        
        self.threshold_var = tk.IntVar(value=self.settings_manager.get("similarity_threshold", 70))
        threshold_scale = ttk.Scale(
            search_frame,
            from_=1,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.threshold_var,
            length=200
        )
        threshold_scale.grid(row=1, column=1, sticky=tk.W, pady=(10, 0))
        
        self.threshold_label = ttk.Label(search_frame, text=f"{self.threshold_var.get()}%")
        threshold_scale.config(command=lambda val: self.threshold_label.config(text=f"{int(float(val))}%"))
        self.threshold_label.grid(row=1, column=2, sticky=tk.W, pady=(10, 0))
        
        # Configure grid weights
        search_frame.columnconfigure(1, weight=1)
        
        # Results frame
        results_frame = ttk.LabelFrame(main_frame, text="Search Results", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create treeview for results
        self.tree = ttk.Treeview(
            results_frame,
            columns=("Filename", "Artist", "Song", "Match Score", "Path", "Info"),
            show="headings",
            selectmode="browse"
        )
        
        # Set up scrollbars
        vsb = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(results_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Pack scrollbars
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Configure columns
        self.tree.column("Filename", width=200, anchor=tk.W)
        self.tree.column("Artist", width=150, anchor=tk.W)
        self.tree.column("Song", width=150, anchor=tk.W)
        self.tree.column("Match Score", width=100, anchor=tk.CENTER)
        self.tree.column("Path", width=300, anchor=tk.W)
        self.tree.column("Info", width=150, anchor=tk.W)
        
        # Add headings
        self.tree.heading("Filename", text="Filename")
        self.tree.heading("Artist", text="Artist")
        self.tree.heading("Song", text="Song")
        self.tree.heading("Match Score", text="Match Score")
        self.tree.heading("Path", text="File Path")
        self.tree.heading("Info", text="File Info")
        
        # Bind double-click to play/preview
        self.tree.bind("<Double-1>", self.preview_file)
        
        # Create context menu
        self.create_context_menu()
    
    def create_context_menu(self):
        """Create right-click context menu for results"""
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Copy File", command=self.copy_selected_file)
        self.context_menu.add_command(label="Copy Path", command=self.copy_file_path)
        self.context_menu.add_command(label="Open Containing Folder", command=self.open_file_location)
        
        # Bind right-click to show menu
        self.tree.bind("<Button-3>", self.show_context_menu)
    
    def show_context_menu(self, event):
        """Show context menu on right-click"""
        # Select the item under the cursor
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
    
    def copy_selected_file(self):
        """Copy the selected file to the output directory"""
        selected = self.tree.selection()
        if not selected:
            return
        
        # Get the file path
        path = self.tree.item(selected[0], "values")[4]
        
        # Get output directory
        output_dir = self.settings_manager.get("output_directory", "")
        if not output_dir:
            output_dir = os.path.join(os.getcwd(), "export")
        
        # Ask for confirmation
        if not os.path.exists(output_dir):
            if not messagebox.askyesno("Create Directory", 
                                      f"Output directory '{output_dir}' does not exist. Create it?"):
                return
            os.makedirs(output_dir, exist_ok=True)
        
        try:
            # Copy the file
            filename = os.path.basename(path)
            dest_path = os.path.join(output_dir, filename)
            
            # Check if file already exists
            if os.path.exists(dest_path):
                # Find a unique name with a counter
                name, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(os.path.join(output_dir, f"{name} ({counter}){ext}")):
                    counter += 1
                dest_path = os.path.join(output_dir, f"{name} ({counter}){ext}")
            
            # Copy the file
            shutil.copy2(path, dest_path)
            
            messagebox.showinfo("Copy Complete", f"File copied to {dest_path}")
            logger.info(f"Copied {path} to {dest_path}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy file: {str(e)}")
            logger.error(f"Failed to copy {path}: {str(e)}")
    
    def copy_file_path(self):
        """Copy the file path to clipboard"""
        selected = self.tree.selection()
        if not selected:
            return
        
        # Get the file path
        path = self.tree.item(selected[0], "values")[4]
        
        # Copy to clipboard
        self.clipboard_clear()
        self.clipboard_append(path)
        
        logger.info(f"Copied path to clipboard: {path}")
    
    def open_file_location(self):
        """Open the folder containing the file"""
        selected = self.tree.selection()
        if not selected:
            return
        
        # Get the file path
        path = self.tree.item(selected[0], "values")[4]
        directory = os.path.dirname(path)
        
        try:
            # Open the folder in file explorer
            if os.name == 'nt':  # Windows
                os.startfile(directory)
            elif os.name == 'posix':  # macOS, Linux
                if sys.platform == 'darwin':  # macOS
                    os.system(f'open "{directory}"')
                else:  # Linux
                    os.system(f'xdg-open "{directory}"')
            
            logger.info(f"Opened folder: {directory}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {str(e)}")
            logger.error(f"Failed to open {directory}: {str(e)}")
    
    def preview_file(self, event):
        """Preview or play the selected file"""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        # Get the file path
        path = self.tree.item(item, "values")[4]
        
        try:
            # Try to open the file with the default application
            if os.name == 'nt':  # Windows
                os.startfile(path)
            elif os.name == 'posix':  # macOS, Linux
                if sys.platform == 'darwin':  # macOS
                    os.system(f'open "{path}"')
                else:  # Linux
                    os.system(f'xdg-open "{path}"')
            
            logger.info(f"Playing file: {path}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to play file: {str(e)}")
            logger.error(f"Failed to play {path}: {str(e)}")
    
    def perform_search(self):
        """Perform a search with the current query"""
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Empty Query", "Please enter a search query.")
            return
        
        # Get the threshold
        threshold = self.threshold_var.get() / 100.0
        
        # Clear the tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Check if we need to scan first
        if not self.music_db.music_files:
            messagebox.showinfo("Scan Required", "No music files found. Please scan your directories first.")
            return
        
        # Perform the search
        results = self.music_db.search(query, threshold)
        
        if not results:
            messagebox.showinfo("No Results", "No matching files found.")
            return
        
        # Add results to the tree
        for music_file, score in results:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    music_file.filename,
                    music_file.artist,
                    music_file.song,
                    f"{score:.0%}",
                    music_file.full_path,
                    f"{music_file.metadata.get('length', '')} | {music_file.extension.upper()}"
                )
            )
        
        logger.info(f"Found {len(results)} matches for query: {query}")

class PlaylistMatchTab(ttk.Frame):
    """Tab for matching playlists to music files"""
    
    def __init__(self, parent, music_db, settings_manager):
        super().__init__(parent)
        self.parent = parent
        self.music_db = music_db
        self.settings_manager = settings_manager
        self.playlist_entries = []
        self.playlist_matches = []
        self.current_threshold = self.settings_manager.get("similarity_threshold", 70) / 100.0
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI for playlist matching"""
        # Main layout
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Playlist file selection frame
        file_frame = ttk.LabelFrame(main_frame, text="Playlist File", padding=10)
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        # File selection controls
        ttk.Label(file_frame, text="Playlist File:").grid(row=0, column=0, padx=(0, 5), sticky=tk.W)
        
        self.file_var = tk.StringVar(value=self.settings_manager.get("last_playlist_file", ""))
        file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=50)
        file_entry.grid(row=0, column=1, padx=(0, 5), sticky=tk.EW)
        
        browse_button = ttk.Button(
            file_frame,
            text="Browse...",
            command=self.browse_playlist
        )
        browse_button.grid(row=0, column=2, padx=(0, 5))
        
        load_button = ttk.Button(
            file_frame,
            text="Load Playlist",
            command=self.load_playlist
        )
        load_button.grid(row=0, column=3, padx=(0, 5))
        
        # Configure grid weights
        file_frame.columnconfigure(1, weight=1)
        
        # Playlist content frame
        content_frame = ttk.LabelFrame(main_frame, text="Playlist Content", padding=10)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Playlist content text widget
        self.playlist_text = tk.Text(content_frame, wrap=tk.WORD, height=10)
        self.playlist_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(content_frame, command=self.playlist_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.playlist_text.config(yscrollcommand=scrollbar.set)
        
        # Matching options frame
        options_frame = ttk.LabelFrame(main_frame, text="Matching Options", padding=10)
        options_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Threshold slider
        ttk.Label(options_frame, text="Similarity Threshold:").grid(row=0, column=0, padx=(0, 5), sticky=tk.W)
        
        self.threshold_var = tk.IntVar(value=self.settings_manager.get("similarity_threshold", 70))
        threshold_scale = ttk.Scale(
            options_frame,
            from_=1,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.threshold_var,
            length=200
        )
        threshold_scale.grid(row=0, column=1, sticky=tk.W)
        
        self.threshold_label = ttk.Label(options_frame, text=f"{self.threshold_var.get()}%")
        threshold_scale.config(command=lambda val: self.threshold_label.config(text=f"{int(float(val))}%"))
        self.threshold_label.grid(row=0, column=2, sticky=tk.W)
        
        # Output directory
        ttk.Label(options_frame, text="Output Directory:").grid(row=1, column=0, padx=(0, 5), sticky=tk.W, pady=(10, 0))
        
        self.output_var = tk.StringVar(value=self.settings_manager.get("output_directory", ""))
        output_entry = ttk.Entry(options_frame, textvariable=self.output_var, width=40)
        output_entry.grid(row=1, column=1, padx=(0, 5), sticky=tk.EW, pady=(10, 0))
        
        output_button = ttk.Button(
            options_frame,
            text="Browse...",
            command=self.browse_output
        )
        output_button.grid(row=1, column=2, padx=(0, 5), pady=(10, 0))
        
        # Configure grid weights
        options_frame.columnconfigure(1, weight=1)
        
        # Action buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X)
        
        # Match button
        match_button = ttk.Button(
            buttons_frame,
            text="Find Matches",
            command=self.find_matches
        )
        match_button.pack(side=tk.LEFT, padx=(0, 5))
    
    def browse_playlist(self):
        """Browse for a playlist file"""
        file_path = filedialog.askopenfilename(
            initialdir=os.path.dirname(self.file_var.get()) if self.file_var.get() else os.getcwd(),
            title="Select Playlist File",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if file_path:
            self.file_var.set(file_path)
            self.settings_manager.set("last_playlist_file", file_path)
    
    def browse_output(self):
        """Browse for output directory"""
        directory = filedialog.askdirectory(
            initialdir=self.output_var.get() if self.output_var.get() else os.getcwd(),
            title="Select Output Directory"
        )
        if directory:
            self.output_var.set(directory)
            self.settings_manager.set("output_directory", directory)
    
    def load_playlist(self):
        """Load the playlist file"""
        file_path = self.file_var.get().strip()
        if not file_path:
            messagebox.showwarning("No File", "Please select a playlist file.")
            return
        
        if not os.path.exists(file_path):
            messagebox.showerror("File Not Found", f"File not found: {file_path}")
            return
        
        try:
            # Read the playlist file
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Filter out empty lines
            lines = [line.strip() for line in lines if line.strip()]
            
            self.playlist_entries = lines
            
            # Update the text widget
            self.playlist_text.delete(1.0, tk.END)
            self.playlist_text.insert(tk.END, "\n".join(lines))
            
            # Save the file path in settings
            self.settings_manager.set("last_playlist_file", file_path)
            
            logger.info(f"Loaded playlist with {len(lines)} entries from {file_path}")
            
            messagebox.showinfo("Playlist Loaded", f"Loaded {len(lines)} entries from the playlist.")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load playlist: {str(e)}")
            logger.error(f"Failed to load playlist {file_path}: {str(e)}")
    
    def find_matches(self):
        """Find matches for the playlist entries"""
        # Check if we have a playlist
        if not self.playlist_entries:
            # Try to get entries from the text widget
            text = self.playlist_text.get(1.0, tk.END).strip()
            if not text:
                messagebox.showwarning("No Playlist", "Please load a playlist or enter entries manually.")
                return
            
            # Split the text into lines
            self.playlist_entries = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Check if we need to scan first
        if not self.music_db.music_files:
            messagebox.showinfo("Scan Required", "No music files found. Please scan your directories first.")
            return
        
        # Get the threshold
        self.current_threshold = self.threshold_var.get() / 100.0
        
        # Save the threshold in settings
        self.settings_manager.set("similarity_threshold", self.threshold_var.get())
        
        # Save the output directory in settings
        output_dir = self.output_var.get().strip()
        if output_dir:
            self.settings_manager.set("output_directory", output_dir)
        else:
            output_dir = os.path.join(os.getcwd(), "export")
        
        # Match playlist entries to music files
        self.playlist_matches = self.music_db.match_playlist(self.playlist_entries, self.current_threshold)
        
        # Create a preview window
        preview = PlaylistMatchPreview(
            self,
            self.playlist_matches,
            self.current_threshold,
            output_dir
        )
        
        logger.info(f"Found matches for {sum(1 for _, matches in self.playlist_matches if matches)} of {len(self.playlist_entries)} playlist entries")
    
    def retry_playlist_match(self, new_threshold):
        """Retry matching with a new threshold"""
        self.current_threshold = new_threshold
        self.threshold_var.set(int(new_threshold * 100))
        
        # Save the threshold in settings
        self.settings_manager.set("similarity_threshold", int(new_threshold * 100))
        
        # Match playlist entries to music files
        self.playlist_matches = self.music_db.match_playlist(self.playlist_entries, self.current_threshold)
        
        # Get the output directory
        output_dir = self.output_var.get().strip()
        if not output_dir:
            output_dir = os.path.join(os.getcwd(), "export")
        
        # Create a new preview window
        preview = PlaylistMatchPreview(
            self,
            self.playlist_matches,
            self.current_threshold,
            output_dir
        )
        
        logger.info(f"Retried matching with threshold {new_threshold:.0%}, found matches for {sum(1 for _, matches in self.playlist_matches if matches)} of {len(self.playlist_entries)} playlist entries")

class SpotifyExtractorTab(ttk.Frame):
    """Tab for Spotify playlist extraction"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.spotify_extractor = None
        self.setup_ui()
        self.load_spotify_extractor()
    
    def setup_ui(self):
        """Set up the UI wrapper for Spotify extractor"""
        # Create a frame to hold the Spotify Extractor GUI
        self.extractor_frame = ttk.Frame(self)
        self.extractor_frame.pack(fill=tk.BOTH, expand=True)
        
        # Status label for when extractor can't be loaded
        self.status_label = ttk.Label(
            self.extractor_frame,
            text="Loading Spotify Playlist Extractor...",
            wraplength=400,
            justify=tk.CENTER
        )
        self.status_label.pack(expand=True, pady=20)
    
    def load_spotify_extractor(self):
        """Try to load the Spotify playlist extractor"""
        try:
            # Import the SpotifyExtractorGUI class from the module
            from spotify_extractor import SpotifyExtractorGUI
            
            # Clear the status label
            self.status_label.pack_forget()
            
            # Fix for 'Frame' object has no attribute 'title'
            # Create a frame that will host the extractor GUI
            host_frame = ttk.Frame(self.extractor_frame)
            host_frame.pack(fill=tk.BOTH, expand=True)
            
            # Add a title method to the frame to avoid the error
            host_frame.title = lambda _: None
            
            # Create the extractor GUI in our custom frame
            self.spotify_extractor = SpotifyExtractorGUI(host_frame)
            
            logger.info("Successfully loaded Spotify playlist extractor")
        
        except Exception as e:
            logger.error(f"Error loading Spotify extractor: {str(e)}")
            error_details = traceback.format_exc()
            logger.debug(f"Traceback: {error_details}")
            
            # Update the status label with the error
            self.status_label.config(
                text=f"Error loading Spotify extractor: {str(e)}\n\nPlease check the Console tab for details."
            )

class MusicPlaylistManagerApp:
    """Main application class"""
    
    def __init__(self, root):
        self.root = root
        self.root.title(f"Music Playlist Manager v{__version__}")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # Create the settings manager
        self.settings_manager = SettingsManager()
        
        # Create the music database
        self.music_db = MusicDatabase()
        
        # Load directories from settings
        for directory in self.settings_manager.get("directories", []):
            self.music_db.add_directory(directory)
        
        # Load file extensions from settings
        self.music_db.set_extensions(set(self.settings_manager.get("extensions", ["mp3", "m4a", "flac", "ogg", "aac", "wav"])))
        
        # Set up the UI
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the main application UI"""
        # Create main layout
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Directory selection frame
        dir_frame = ttk.LabelFrame(main_frame, text="Music Directories", padding=10)
        dir_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Directory list
        dir_list_frame = ttk.Frame(dir_frame)
        dir_list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        self.dir_listbox = tk.Listbox(dir_list_frame, height=5, selectmode=tk.SINGLE)
        self.dir_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add scrollbar to directory list
        dir_scrollbar = ttk.Scrollbar(dir_list_frame, orient=tk.VERTICAL, command=self.dir_listbox.yview)
        dir_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.dir_listbox.config(yscrollcommand=dir_scrollbar.set)
        
        # Populate directory list
        for directory in self.music_db.directories:
            self.dir_listbox.insert(tk.END, directory)
        
        # Directory buttons
        dir_buttons_frame = ttk.Frame(dir_frame)
        dir_buttons_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        add_dir_button = ttk.Button(
            dir_buttons_frame,
            text="Add Directory",
            command=self.add_directory
        )
        add_dir_button.pack(fill=tk.X, pady=(0, 5))
        
        remove_dir_button = ttk.Button(
            dir_buttons_frame,
            text="Remove Directory",
            command=self.remove_directory
        )
        remove_dir_button.pack(fill=tk.X)
        
        # File extension checkboxes
        ext_frame = ttk.LabelFrame(main_frame, text="File Extensions", padding=10)
        ext_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Extension variables
        self.extension_vars = {}
        extensions = ["mp3", "m4a", "flac", "ogg", "aac", "wav"]
        
        # Get extensions from settings
        enabled_extensions = set(self.settings_manager.get("extensions", extensions))
        
        # Create a checkbox for each extension
        for i, ext in enumerate(extensions):
            var = tk.BooleanVar(value=ext in enabled_extensions)
            self.extension_vars[ext] = var
            
            cb = ttk.Checkbutton(
                ext_frame,
                text=ext.upper(),
                variable=var,
                command=self.update_extensions
            )
            cb.grid(row=0, column=i, padx=10)
        
        # Scan button and progress frame
        scan_frame = ttk.Frame(main_frame)
        scan_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.scan_button = ttk.Button(
            scan_frame,
            text="Scan Music Files",
            command=self.scan_directories
        )
        self.scan_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.progress_frame = ttk.Frame(scan_frame)
        self.progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.progress_var = tk.StringVar(value="Ready")
        progress_label = ttk.Label(self.progress_frame, textvariable=self.progress_var)
        progress_label.pack(side=tk.TOP, fill=tk.X)
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="determinate", length=200)
        self.progress_bar.pack(side=tk.TOP, fill=tk.X, expand=True)
        
        # Initially hide the progress bar
        self.progress_bar.pack_forget()
        
        # Create notebook (tabs)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Create tabs
        self.search_tab = ManualSearchTab(self.notebook, self.music_db, self.settings_manager)
        self.notebook.add(self.search_tab, text="Search")
        
        self.playlist_tab = PlaylistMatchTab(self.notebook, self.music_db, self.settings_manager)
        self.notebook.add(self.playlist_tab, text="Playlist Matching")
        
        # Create Spotify Extractor tab
        self.spotify_tab = SpotifyExtractorTab(self.notebook)
        self.notebook.add(self.spotify_tab, text="Spotify Extractor")
        
        # Create console tab
        self.console_tab = ConsoleTab(self.notebook)
        self.notebook.add(self.console_tab, text="Console")
        
        # Status bar
        self.status_var = tk.StringVar(value=f"Music Playlist Manager v{__version__}")
        status_bar = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(10, 2)
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Log application start
        logger.info(f"Music Playlist Manager v{__version__} started")
        logger.info(f"Loaded {len(self.music_db.directories)} directories and {len(enabled_extensions)} file extensions")
    
    def add_directory(self):
        """Add a directory to scan"""
        directory = filedialog.askdirectory(
            title="Select Music Directory",
            initialdir=self.music_db.directories[0] if self.music_db.directories else os.getcwd()
        )
        
        if directory:
            if self.music_db.add_directory(directory):
                self.dir_listbox.insert(tk.END, directory)
                self.settings_manager.set("directories", self.music_db.directories)
                logger.info(f"Added directory: {directory}")
            else:
                logger.warning(f"Directory already in list: {directory}")
    
    def remove_directory(self):
        """Remove a directory from the list"""
        selected = self.dir_listbox.curselection()
        if not selected:
            return
        
        index = selected[0]
        directory = self.dir_listbox.get(index)
        
        if self.music_db.remove_directory(directory):
            self.dir_listbox.delete(index)
            self.settings_manager.set("directories", self.music_db.directories)
            logger.info(f"Removed directory: {directory}")
    
    def update_extensions(self):
        """Update file extensions based on checkboxes"""
        enabled_extensions = {ext for ext, var in self.extension_vars.items() if var.get()}
        self.music_db.set_extensions(enabled_extensions)
        self.settings_manager.set("extensions", list(enabled_extensions))
        logger.info(f"Updated file extensions: {', '.join(enabled_extensions)}")
    
    def scan_directories(self):
        """Scan directories for music files"""
        # Check if we have directories to scan
        if not self.music_db.directories:
            messagebox.showwarning("No Directories", "Please add at least one music directory.")
            return
        
        # Start the scan
        logger.info(f"Starting scan of {len(self.music_db.directories)} directories...")
        
        # Display progress bar
        self.progress_bar.config(value=0, maximum=100)
        self.progress_bar.pack(side=tk.TOP, fill=tk.X, expand=True)
        
        # Disable scan button during scan
        self.scan_button.config(state=tk.DISABLED)
        
        # Start the scan
        self.music_db.scan_directories(self.update_scan_progress)
    
    def update_scan_progress(self, current, total, message):
        """Update the scan progress"""
        self.progress_var.set(message)
        
        if total > 0:
            progress = (current / total) * 100
            self.progress_bar.config(value=progress)
        
        # If scan is complete, re-enable the scan button
        if current == total or message.startswith("Error") or message.endswith("cancelled."):
            self.scan_button.config(state=tk.NORMAL)
            
            # Hide progress bar after a delay
            self.root.after(3000, lambda: self.progress_bar.pack_forget())
            
            # Set status bar message
            self.status_var.set(f"Music Playlist Manager v{__version__} - {message}")
        else:
            # Update status bar
            self.status_var.set(f"Scanning... {message}")

def main():
    """Main entry point"""
    # Create the Tkinter root window
    root = tk.Tk()
    
    # Set application icon if available
    # try:
    #     # On Windows
    #     if os.name == 'nt':
    #         root.iconbitmap('icon.ico')
    #     # On Linux/Mac
    #     else:
    #         img = tk.PhotoImage(file='icon.png')
    #         root.tk.call('wm', 'iconphoto', root._w, img)
    # except Exception:
    #     pass  # If icon can't be loaded, just use the default
    
    # Create the application
    app = MusicPlaylistManagerApp(root)
    
    # Start the main loop
    root.mainloop()

if __name__ == "__main__":
    main()
