# File Manager Feature for PT Management

## Overview

The File Manager is a new admin interface feature that allows administrators to create, read, modify, and delete files in the `/shared` folder directly from the PT Management web interface. This eliminates the need to SSH into the server for file management operations.

## Features

- **List Files & Folders**: Browse the complete contents of `/shared`
- **Create Files**: Create new text files with optional initial content
- **Create Folders**: Create new directories for organization
- **View & Edit Files**: Open and edit text files in an in-browser editor
- **Save Changes**: Write changes back to disk
- **Rename Files**: Rename files and directories
- **Delete Files**: Remove files and directories (with confirmation)
- **File Info**: View file sizes and modification timestamps
- **Safety**: 
  - Path traversal protection (all operations confined to `/shared`)
  - File size limits (max 10MB for editing)
  - Permission checks
  - Confirmation dialogs for destructive actions

## Access

1. **Navigate to File Manager**: Click "File Manager" in the PT Management navbar
2. **Authentication**: You must be logged in with admin credentials
3. **URL**: `http://your-server:8080/files`

## API Endpoints

All endpoints are prefixed with `/api/files` and require authentication.

### List Files
```
GET /api/files/
```

Response:
```json
{
  "success": true,
  "path": "/shared",
  "items": [
    {
      "name": "example.txt",
      "path": "example.txt",
      "type": "file",
      "size": 1024,
      "modified": 1609459200,
      "readable": true,
      "writable": true
    },
    {
      "name": "configs",
      "path": "configs",
      "type": "directory",
      "size": 0,
      "modified": 1609459200,
      "readable": true,
      "writable": true
    }
  ]
}
```

### Read File
```
GET /api/files/<filename>
```

Response:
```json
{
  "success": true,
  "path": "example.txt",
  "content": "file contents...",
  "is_binary": false,
  "size": 1024
}
```

### Create/Update File
```
POST /api/files/<filename>
Content-Type: application/json

{
  "content": "new file contents",
  "mode": "w"    // "w" for overwrite (default), "a" for append
}
```

Response:
```json
{
  "success": true,
  "path": "example.txt",
  "message": "File saved successfully",
  "size": 1024
}
```

### Create Directory
```
POST /api/files/mkdir/<dirname>
```

Response:
```json
{
  "success": true,
  "path": "configs",
  "message": "Directory created successfully"
}
```

### Rename File
```
POST /api/files/rename
Content-Type: application/json

{
  "old_path": "oldname.txt",
  "new_path": "newname.txt"
}
```

Response:
```json
{
  "success": true,
  "old_path": "oldname.txt",
  "new_path": "newname.txt",
  "message": "File renamed successfully"
}
```

### Delete File/Directory
```
DELETE /api/files/<filename>
```

Response:
```json
{
  "success": true,
  "path": "example.txt",
  "message": "File/directory deleted successfully"
}
```

## Security Considerations

### Path Traversal Protection
The file manager validates all file paths to ensure they remain within `/shared`. Attempts to access parent directories (`../`) or absolute paths outside `/shared` are rejected with a `400` error.

### File Size Limits
- **Read operations**: Limited to 10MB per file to prevent memory issues
- **Binary files**: Served as base64-encoded content for safe transmission

### Permission Checks
- All file operations check filesystem permissions
- Operations on read-only files are rejected
- Requires admin authentication for all operations

### Error Handling
- Clear error messages for common issues (file not found, permission denied, etc.)
- HTTP status codes:
  - `200`: Success
  - `201`: Created (for new directories)
  - `400`: Invalid path or missing required fields
  - `403`: Permission denied
  - `404`: File/folder not found
  - `409`: Resource already exists
  - `413`: File too large
  - `500`: Server error

## Usage Examples

### Using curl

**List files:**
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/files/
```

**Create a file:**
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"content":"Hello World"}' \
  http://localhost:8080/api/files/hello.txt
```

**Edit a file:**
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"content":"Updated content"}' \
  http://localhost:8080/api/files/hello.txt
```

**Create a directory:**
```bash
curl -X POST http://localhost:8080/api/files/mkdir/newdir
```

**Rename a file:**
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"old_path":"old.txt","new_path":"new.txt"}' \
  http://localhost:8080/api/files/rename
```

**Delete a file:**
```bash
curl -X DELETE http://localhost:8080/api/files/hello.txt
```

## Implementation Details

### Files Modified
- `app.py`: Added `/files` route and registered file manager API blueprint
- `templates/dashboard.html`: Added File Manager link to navbar
- `ptmanagement/api/file_manager.py`: New module containing all file management logic

### Key Functions

**Validation:**
- `validate_path()`: Ensures requested path stays within `/shared`

**API Functions:**
- `list_files()`: GET - List directory contents
- `read_file()`: GET - Read file content
- `write_file()`: POST - Create/update files
- `create_directory()`: POST - Create directories
- `delete_file()`: DELETE - Remove files/directories
- `rename_file()`: POST - Rename files/directories

### Frontend

The HTML template provides:
- File browser with inline actions
- Modal dialogs for create, rename, and delete operations
- In-browser text editor for file editing
- Real-time file information (size, modification date)
- Notification system for user feedback

## Testing the Feature

1. **Start the PT Management service:**
   ```bash
   docker-compose -f ptweb-vnc/docker-compose.yml up pt-management
   ```

2. **Log in** with admin credentials

3. **Access File Manager** via the navbar

4. **Try operations:**
   - Create a test file
   - Edit its contents
   - Create a folder
   - Rename files
   - Delete test files

## Troubleshooting

### "Permission denied" errors
- Ensure `/shared` is writable by the Docker container user
- Check file/folder permissions: `ls -la /shared`

### "File too large" errors
- Edit limit is 10MB; use command-line tools for larger files
- Binary files are displayed as base64-encoded text (read-only)

### Files not appearing
- Click "Refresh" button
- Check that files are actually in `/shared`
- Verify container has read permissions

### Cannot save changes
- Ensure file is writable: `chmod 644 /shared/filename`
- Check disk space: `df -h /shared`

## Future Enhancements

- Directory navigation/breadcrumbs
- File upload via drag-and-drop
- Download files as .zip
- Syntax highlighting for code files
- Search functionality
- File permissions editor
- Access logs/audit trail

## Related Documentation

- [PT Management README](../README.md)
- [Shared Folder Information](../MANAGEMENT_INTERFACE_FIX.md)
- API Authentication: See `ptmanagement/api/auth.py`
