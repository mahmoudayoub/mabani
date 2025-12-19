# Python Runtime Fix

## Problem

The 502 error was caused by **serverless-offline not supporting Python 3.13**. The error message showed:

```
Warning: found unsupported runtime 'python3.13' for function 'listKnowledgeBases'
✖ Unsupported runtime
```

## Solution

Changed the runtime from `python3.13` to `python3.12` in `serverless.yml`. This is because:

1. **serverless-offline** only supports up to Python 3.12
2. Python 3.13 is too new for serverless-offline
3. AWS Lambda supports Python 3.12, which works fine

## What Changed

```yaml
# Before:
runtime: python3.13

# After:
runtime: python3.12
```

## Next Steps

1. **Restart the server** (important!):

   ```bash
   # Stop the server (Ctrl+C)
   cd backend
   ./local-server.sh
   ```

2. **Test the health endpoint**:

   ```bash
   curl http://localhost:3001/health
   ```

3. **Test your knowledge-bases endpoint** - it should work now!

## Note

- For **local development**: Use Python 3.12 (required by serverless-offline)
- For **production/deployment**: You can still deploy with Python 3.13 if needed, but for consistency, using 3.12 is recommended

## Verify Python Version

Make sure you have Python 3.12 available:

```bash
python3.12 --version
```

If you need to install Python 3.12:

```bash
# Using pyenv
pyenv install 3.12.0
pyenv local 3.12.0
```
