from flask import Flask, jsonify
from flask_cors import CORS
from detect import detect_intrusion

app = Flask(__name__)
CORS(app)

@app.route('/api/intrusion')
def intrusion():
    print("API CALLED")
    result = detect_intrusion()
    return jsonify({"intrusion": result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
    