def try_import(name):
    try:
        module = __import__(name)
        version = getattr(module, "__version__", "loaded")
        log("<color=#98c379><b>Import OK:</b></color> <color=#f8f8f2>" + name + " (" + str(version) + ")</color>")
    except Exception as exc:
        log("<color=#e06c75><b>Import failed:</b></color> <color=#f8f8f2>" + name + " - " + str(exc) + "</color>")

for module_name in ["os", "json", "random", "math", "datetime", "six", "decorator"]:
    try_import(module_name)
