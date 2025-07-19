import os
from datetime import datetime
import time
from functools import wraps


## 3rd party libs
import json

def get_git_root(startpath=os.getcwd()):
    current_path = os.path.abspath(startpath) # Path started on
    while True:
        if os.path.isdir(os.path.join(current_path, '.git')) or os.path.isfile(os.path.join(current_path, 'README.md')): # If on git path, return it
            ret = current_path
            break
        else:
            ret = current_path
        
        parent_path = os.path.dirname(current_path)

        if parent_path == current_path: # If current path is parent path, stop 
            break
        current_path = parent_path # Set current path to parent path, to check if git path again

    if ret:
        return ret.replace("\\", "/")
    else:
        return None

def get_current_time():
    return datetime.now().strftime("%H:%M:%S")

def print_time():
    print(get_current_time)

def printline():
    print("---" * 50)

def log_time(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()  # Record start time
        printline()
        print(f"Started {func.__name__} at {get_current_time()}")
        result = func(*args, **kwargs)
        end_time = time.time()  # Record end time
        elapsed_time = end_time - start_time  # Calculate elapsed time
        print(f"Finished {func.__name__} at {get_current_time()}")
        print(f"Total time elapsed: {elapsed_time:.4f} seconds")  # Print elapsed time
        printline()
        print("\n")
        return result
    return wrapper

def print_dict(dictionary):
    print(json.dumps(dictionary, indent=4))


if __name__ == "__main__":
    print("job")
