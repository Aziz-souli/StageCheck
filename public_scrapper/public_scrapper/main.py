# main.py
import sys
import uvicorn

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        # Run FastAPI server
        uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
    else:
        # Run CLI
        from cli import main
        main()