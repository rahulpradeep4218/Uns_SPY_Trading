
from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys
import pyperclip
import time
import pyautogui

def tos_order():
    order_text = pyperclip.paste()

    if not order_text.strip():
        print("Clipboard is empty or contains only whitespace.")
        return {"status": "error", "message": "Clipboard is empty or contains only whitespace."}

    if not "BUY" in order_text:
        print("Order text does not contain 'BUY', so its not looking correct")
        print(f"Current clipboard content: {order_text}")
        return {"status": "error", "message": "Order text does not contain 'BUY'."}
  
    try:
        main_window = Desktop(backend="win32").window(title_re="Main@thinkorswim.*")
        print("Process ID:", main_window.process_id())
        app = Application(backend="win32").connect(process=main_window.process_id())
        # for w in app.windows():
        #     print("-" , w.window_text(), w.class_name(), w.handle, w.is_visible())
    except Exception as e:
        print(f"Error connecting to Thinkorswim application: {e}")
        return {"status": "error", "message": f"Error connecting to Thinkorswim application: {e}"}

    tos_window = app.window(title_re=".*thinkorswim.*")
    tos_window.set_focus()

    if "\\n" in order_text:
        print("Order text contains newlines, splitting on that.")
        orders = [line.strip() for line in order_text.split("\\n") if line.strip()]
    else:
        orders = [line.strip() for line in order_text.splitlines() if line.strip()]

    if not orders:
        print("No valid orders found in the clipboard text.")
        return {"status": "error", "message": "No valid orders found in the clipboard text."}
    
    for order in orders:
        print(f"Processing order: {order}")
        pyperclip.copy(order)
        time.sleep(0.5)
        press_clipboard_button()
        time.sleep(1.5)

    return {"status": "success", "message": f"Order pasted successfully : {order_text}"}




def press_clipboard_button():
    location = pyautogui.locateOnScreen('clipboard_icon.png', confidence=0.8)
    if location:
        center = pyautogui.center(location)
        print(f" Found paste button at {center}")
        pyautogui.moveTo(center)
        pyautogui.click()
        print("Clicked on the clipboard button.")
    
        
if __name__ == "__main__":
    #result = tos_order()
    #print(result)
    tos_order()