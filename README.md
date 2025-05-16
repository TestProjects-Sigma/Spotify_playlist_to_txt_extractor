# Music Playlist to TXT Extractor

**Version 1.0.0**

A Python application to manage music files and playlists with smart matching and file organization.

## Features

- **Multi-directory scanning**: Scan multiple music directories recursively
- **Smart filename parsing**: Intelligently extract artist and song information from filenames
- **Flexible search**: Search by artist, song, or both with smart word-based matching
- **Playlist matching with preview**: Match playlist entries to your music files, preview results, and copy matches
- **Customizable similarity threshold**: Adjust matching precision with a similarity slider
- **File extension filtering**: Select which audio file types to include
- **Settings management**: Save and load your configurations
- **Detailed logging**: Track operations in the console tab
- **Spotify playlist integration**: Extract Spotify playlists using the integrated Spotify Extractor

## Installation

### Prerequisites

- Python 3.6 or higher
- pip (Python package installer)

### Windows Installation with Virtual Environment

Setting up a virtual environment is recommended to avoid conflicts with other Python packages. Follow these steps:

1. **Download the Source Code**
   - Download and extract the application files to a folder of your choice

2. **Open Command Prompt**
   - Press `Win + R`, type `cmd`, and press Enter
   - Navigate to your project folder:
     ```
     cd path\to\your\folder
     ```

3. **Create a Virtual Environment**
   - Create a new virtual environment named 'venv':
     ```
     python -m venv venv
     ```
   - Activate the virtual environment:
     ```
     venv\Scripts\activate
     ```
   - You should see `(venv)` at the beginning of your command prompt line

4. **Install Dependencies**
   - Install required packages:
     ```
     pip install -r requirements.txt
     ```

5. **Run the Application**
   - Start the application:
     ```
     python MusicPlaylistManager.py
     ```

6. **Deactivating the Virtual Environment**
   - When you're done, you can deactivate the virtual environment:
     ```
     deactivate
     ```

### Basic Installation (Alternative)

If you prefer not to use a virtual environment:

```bash
pip install tkinter
```

### Enhanced Installation (for ID3 tag support)

For full functionality including ID3 tag support, install these additional packages:

```bash
pip install mutagen
```

## Usage

### Running the Application

Run the application with:

```bash
python MusicPlaylistManager.py
```

### Quick Start Guide

1. **Add Music Directories**:
   - Click "Add Directory" to select folders containing your music files

2. **Select File Extensions**:
   - Choose which file types to include in your scans (mp3, flac, etc.)

3. **Scan Music Files**:
   - Click "Scan Music Files" to build the music database

4. **Search for Music**:
   - Use the "Search" tab to find music by artist, song, or filename

5. **Match Playlists**:
   - In the "Playlist Matching" tab, load a playlist file and find matches
   - Review matches and copy selected files to your desired location

6. **Extract Spotify Playlists**:
   - Use the "Spotify Extractor" tab to download playlists from Spotify

## Filename Parsing

The application supports multiple filename formats:
- "Artist - Song"
- "Artist_-_Song" 
- "Artist_Song"
- "01 - Artist - Song" (with track numbers)
- "01_-_Artist_-_Song" (with track numbers and underscores)

or 

- "Song - Artist"
- "Song_-_Artist" 
- "Song_Artist"
- "01 - Song - Artist" (with track numbers)
- "01_-_Song_-_Artist" (with track numbers and underscores)

## Word-Based Searching

The search feature splits your query into individual words and finds files where ALL words appear somewhere in the filename, artist, or song fields. This allows flexible searching regardless of word order or separators.

## Fuzzy Matching

For both searches and playlist matching, the application uses fuzzy string matching techniques to find similar items even when spellings aren't exact.

## Preview Window Features

- **Detailed match table**: See all matched files with their details:
  - Original playlist entry
  - Matched filename
  - Match score (percentage)
  - Full file path
  - Music file metadata
  
- **Interactive controls**:
  - Adjust similarity threshold on-the-fly
  - "Retry with New Threshold" button to immediately see how changes affect matches
  - Change output directory before copying
  - Cancel to abort without copying anything
  - File selection (checkbox) to manually select files to copy to output folder

## Spotify Playlist Extractor

The application integrates the Spotify Playlist Extractor, which allows you to:
- Extract playlists from Spotify
- Save them as text files that can be used with the playlist matching feature
- Requires Spotify API credentials (client ID and client secret)

## Additional Information

- **Settings**: The application automatically saves your settings and directories
- **File Operations**: Double-click on files in search results to play them with your default media player
- **Context Menu**: Right-click on search results for additional options

## Troubleshooting

- **Missing Spotify Extractor**: If you see an error loading the Spotify extractor, make sure the `spotify_extractor.py` file is in the same directory as `MusicPlaylistManager.py`
- **File Scanning Issues**: If scanning is slow, try selecting fewer directories or file extensions
- **Playback Problems**: The application uses your system's default media player; make sure it's properly configured

## License

This software is provided as-is under the MIT License.

## Acknowledgments

- Uses the difflib library for fuzzy string matching
- Spotify Extractor component for playlist integration

---

Created with ❤️ for music lovers who want to organize their collections
