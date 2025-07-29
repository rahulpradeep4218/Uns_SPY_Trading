import jpype


jvm_path = r"C:\Users\coool\AppData\Local\thinkorswim\jre_1984.1.0\bin\server\jvm.dll"

def start_jvm():
    if not jpype.isJVMStarted():
        jpype.startJVM(jvm_path)

    print("JVM started successfully.")

    print("Is JVM running?", jpype.isJVMStarted())