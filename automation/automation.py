from fastapi import FastAPI
import keyboard
import threading
from methods import tos_order
import uvicorn

app = FastAPI()

@app.post("/trigger-tos-order")
def trigger_tos_order():
    try:
        response = tos_order()
        return response
    except Exception as e:
        return {"status": "error", "message": str(e)}
    

def on_hotkey():
    print("Ctrl + Alt + N Hotkey pressed, triggering TOS order...")
    try:
        response = tos_order()
        print(response)
    except Exception as e:
        print({"status": "error", "message": f"Error when triggering through hot key : {str(e)}"})


def run_fastapi():
    uvicorn.run(app, host="127.0.0.1", port=9369)

if __name__ == "__main__":
    api_thread = threading.Thread(target=run_fastapi, daemon=True)
    api_thread.start()
    print("FastAPI server started on http://127.0.0.1:9369")

    # Register hotkey
    keyboard.add_hotkey('ctrl+alt+n', on_hotkey)
    print("🎯 Press Ctrl + Alt + N to trigger TOS order.")
    print("❌ Stop service anytime with CTRL + C in this terminal.")

    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("Exiting, Service stopped manually...")