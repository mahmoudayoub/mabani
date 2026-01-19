from twilio.rest import Client
import inspect

try:
    print("Checking Twilio Library...")
    import twilio
    print(f"Twilio Version: {twilio.__version__}")
    
    client = Client("ACxxx", "xxx")
    
    try:
        content_v1 = client.content.v1
        print("client.content.v1:", content_v1)
        
        contents = content_v1.contents
        print("client.content.v1.contents:", contents)
        print("Type:", type(contents))
        print("Dir:", dir(contents))
        
        if hasattr(contents, 'create'):
            print("Has 'create' method.")
        else:
            print("NO 'create' method found.")
            
    except Exception as e:
        print(f"Error accessing content: {e}")

except Exception as e:
    print(f"Main Error: {e}")
