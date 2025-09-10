# check_env.py
import sys
import os

try:
    # Print the exact path of the Python interpreter being used
    print(f"--- Python Executable ---")
    print(sys.executable)
    print("-" * 25)

    # Import the library and print its version
    import google.generativeai as genai
    print(f"--- Google AI Library Version ---")
    print(genai.__version__)
    print("-" * 25)
    
    # Print the path where the library was found
    print(f"--- Library Location ---")
    print(genai.__file__)
    print("-" * 25)

except ImportError:
    print("\nERROR: The 'google-generativeai' library is NOT INSTALLED for this Python interpreter.")
except Exception as e:
    print(f"\nAn unexpected error occurred: {e}")