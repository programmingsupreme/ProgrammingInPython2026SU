from flask import Flask, render_template, request
import requests
from PIL import Image
from io import BytesIO
import base64

app = Flask(__name__)


# Function to fetch Mars Rover photos
def fetch_mars_rover_photos(api_key, sol, camera):
    url = 'https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/photos'
    params = {
        'sol': sol,
        'camera': camera,
        'api_key': api_key
    }
    response = requests.get(url, params=params)
    return response.json()


# Route for the home page
@app.route('/', methods=['GET', 'POST'])
def home():
    photos = []
    if request.method == 'POST':
        sol = request.form.get('sol')
        camera = request.form.get('camera')
        api_key = 'DEMO_KEY'  # Replace with your actual NASA API key
        photos_data = fetch_mars_rover_photos(api_key, sol, camera)

        if 'photos' in photos_data:
            for photo in photos_data['photos']:
                img_url = photo['img_src']
                response = requests.get(img_url)
                img_data = response.content
                img = Image.open(BytesIO(img_data))
                buffered = BytesIO()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                photos.append((photo['id'], photo['earth_date'], img_str))

    return render_template('index.html', photos=photos)


if __name__ == '__main__':
    app.run(debug=True)
