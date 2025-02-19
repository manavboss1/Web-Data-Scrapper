from pyngrok import ngrok

# Open an HTTP tunnel on the default port 5000
public_url = ngrok.connect(port='5000')
print("Public URL:", public_url)

app.run()
