from flask import Flask, render_template, request, jsonify
import time

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    # Simulate network latency over a WAN
    time.sleep(1) # 1 second delay
    
    data = request.json
    username = data.get('username', '')
    email = data.get('email', '')
    password = data.get('password', '')
    
    errors = []
    
    if len(username) < 5:
        errors.append("Username must be at least 5 characters long.")
    if "@" not in email or "." not in email:
        errors.append("Invalid email address format.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
        
    if errors:
        return jsonify({"success": False, "errors": errors})
    else:
        return jsonify({"success": True, "message": "Registration successful!"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
