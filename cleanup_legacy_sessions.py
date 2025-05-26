#!/usr/bin/env python3
"""
Legacy Session Cleanup Script

This script helps migrate from the old file-based session storage
to the new centralized in-memory session management system.

Features:
- Analyzes legacy session files
- Optionally migrates active sessions to new system
- Cleans up old session files
- Provides detailed report
"""

import json
import os
import time
from datetime import datetime, timedelta
import shutil

def load_session_file(filepath):
    """Load a session file and return its data"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def analyze_legacy_sessions():
    """Analyze all legacy session files"""
    play_sessions_dir = 'play_sessions'
    
    if not os.path.exists(play_sessions_dir):
        print("No play_sessions directory found")
        return
    
    files = [f for f in os.listdir(play_sessions_dir) if f.endswith('.json')]
    
    print(f"Found {len(files)} session files")
    
    active_sessions = []
    completed_sessions = []
    corrupted_sessions = []
    group_next_files = []
    
    current_time = time.time()
    
    for filename in files:
        filepath = os.path.join(play_sessions_dir, filename)
        
        # Handle group next quiz files separately
        if filename.startswith('group_') and filename.endswith('_next.json'):
            group_next_files.append(filename)
            continue
        
        session_data = load_session_file(filepath)
        
        if not session_data:
            corrupted_sessions.append(filename)
            continue
        
        try:
            # Check if session is complete
            current_question = session_data.get('current_question', 0)
            total_questions = len(session_data.get('questions', []))
            is_complete = current_question >= total_questions
            
            # Check session age
            started_at = datetime.fromisoformat(session_data.get('started_at', ''))
            age_hours = (datetime.now() - started_at).total_seconds() / 3600
            
            session_info = {
                'filename': filename,
                'session_id': session_data.get('session_id'),
                'quiz_id': session_data.get('quiz_id'),
                'quiz_title': session_data.get('quiz_title', 'Unknown'),
                'player_name': session_data.get('player_name', 'Unknown'),
                'is_complete': is_complete,
                'age_hours': age_hours,
                'progress': f"{current_question}/{total_questions}",
                'group_id': session_data.get('shared_session_group')
            }
            
            if is_complete or age_hours > 24:  # Consider old sessions as completed
                completed_sessions.append(session_info)
            else:
                active_sessions.append(session_info)
                
        except Exception as e:
            print(f"Error analyzing {filename}: {e}")
            corrupted_sessions.append(filename)
    
    # Print analysis report
    print("\n" + "="*80)
    print("LEGACY SESSION ANALYSIS REPORT")
    print("="*80)
    
    print(f"\nActive Sessions: {len(active_sessions)}")
    for session in active_sessions:
        print(f"  {session['filename']}: {session['quiz_title']} - {session['player_name']} ({session['progress']}, {session['age_hours']:.1f}h old)")
    
    print(f"\nCompleted/Old Sessions: {len(completed_sessions)}")
    for session in completed_sessions[:10]:  # Show first 10
        print(f"  {session['filename']}: {session['quiz_title']} - {session['player_name']} ({session['progress']}, {session['age_hours']:.1f}h old)")
    if len(completed_sessions) > 10:
        print(f"  ... and {len(completed_sessions) - 10} more")
    
    print(f"\nGroup Next Quiz Files: {len(group_next_files)}")
    for filename in group_next_files:
        print(f"  {filename}")
    
    print(f"\nCorrupted Sessions: {len(corrupted_sessions)}")
    for filename in corrupted_sessions:
        print(f"  {filename}")
    
    print(f"\nTotal Files: {len(files)}")
    print(f"Recommended for cleanup: {len(completed_sessions) + len(corrupted_sessions) + len(group_next_files)}")
    
    return {
        'active': active_sessions,
        'completed': completed_sessions,
        'corrupted': corrupted_sessions,
        'group_next': group_next_files
    }

def backup_session_files():
    """Create a backup of all session files"""
    play_sessions_dir = 'play_sessions'
    backup_dir = f'play_sessions_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    
    if not os.path.exists(play_sessions_dir):
        print("No play_sessions directory to backup")
        return None
    
    try:
        shutil.copytree(play_sessions_dir, backup_dir)
        print(f"Created backup: {backup_dir}")
        return backup_dir
    except Exception as e:
        print(f"Error creating backup: {e}")
        return None

def cleanup_legacy_files(analysis_result, keep_active=True):
    """Clean up legacy session files based on analysis"""
    play_sessions_dir = 'play_sessions'
    
    files_to_remove = []
    
    # Always remove corrupted files and group next files
    files_to_remove.extend([f"corrupted"]*len(analysis_result['corrupted']))
    files_to_remove.extend([f"group_next"]*len(analysis_result['group_next']))
    
    # Remove completed/old sessions
    files_to_remove.extend([f"completed"]*len(analysis_result['completed']))
    
    # Optionally remove active sessions if migrated
    if not keep_active:
        files_to_remove.extend([f"active"]*len(analysis_result['active']))
    
    all_files_to_remove = (
        [s['filename'] for s in analysis_result['completed']] +
        analysis_result['corrupted'] +
        analysis_result['group_next']
    )
    
    if not keep_active:
        all_files_to_remove.extend([s['filename'] for s in analysis_result['active']])
    
    print(f"\nRemoving {len(all_files_to_remove)} files...")
    
    removed_count = 0
    for filename in all_files_to_remove:
        filepath = os.path.join(play_sessions_dir, filename)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                removed_count += 1
                print(f"  Removed: {filename}")
        except Exception as e:
            print(f"  Error removing {filename}: {e}")
    
    print(f"\nSuccessfully removed {removed_count} files")
    
    # Check if directory is empty and remove it
    remaining_files = os.listdir(play_sessions_dir) if os.path.exists(play_sessions_dir) else []
    if len(remaining_files) == 0:
        try:
            os.rmdir(play_sessions_dir)
            print(f"Removed empty directory: {play_sessions_dir}")
        except Exception as e:
            print(f"Could not remove directory {play_sessions_dir}: {e}")
    else:
        print(f"Directory {play_sessions_dir} still contains {len(remaining_files)} files")

def main():
    """Main function"""
    print("Legacy Session Cleanup Tool")
    print("="*50)
    
    # Analyze current state
    analysis_result = analyze_legacy_sessions()
    
    if not analysis_result:
        print("No session files found or analysis failed")
        return
    
    # Ask user what to do
    print("\nOptions:")
    print("1. Create backup only")
    print("2. Create backup and cleanup completed/corrupted files (keep active)")
    print("3. Create backup and cleanup all files")
    print("4. Exit without changes")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == '1':
        backup_session_files()
        print("Backup created. No files removed.")
        
    elif choice == '2':
        backup_dir = backup_session_files()
        if backup_dir:
            cleanup_legacy_files(analysis_result, keep_active=True)
            print(f"\nCleanup completed. Backup available at: {backup_dir}")
        
    elif choice == '3':
        backup_dir = backup_session_files()
        if backup_dir:
            cleanup_legacy_files(analysis_result, keep_active=False)
            print(f"\nFull cleanup completed. Backup available at: {backup_dir}")
        
    elif choice == '4':
        print("No changes made.")
        
    else:
        print("Invalid choice. No changes made.")

if __name__ == "__main__":
    main() 