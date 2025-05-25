# 🎮 This or That - Tinder-Style Quiz Game

A beautiful web application where you can create and play "This or That" quizzes with a Tinder-like swiping interface!

## ✨ Features

- **🎨 Beautiful Tinder-like Interface**: Swipe left or right to make your choices
- **📷 Image Upload**: Upload images and automatically extract questions using OCR
- **🛠️ Manual Creation**: Create quizzes manually with a rich editor
- **🔗 Easy Sharing**: Share quizzes with friends using unique IDs
- **📱 Responsive Design**: Works perfectly on desktop and mobile
- **🎯 No Accounts Required**: Start playing immediately
- **🎪 Beautiful Icons**: Automatic icon assignment based on content
- **⚡ Real-time Progress**: Live progress tracking and smooth animations

## 🚀 Quick Start

### Prerequisites

- Python 3.7 or higher
- Tesseract OCR (for image processing)

### Windows Installation

1. **Install Tesseract OCR**:
   - Download from: https://github.com/UB-Mannheim/tesseract/wiki
   - Add to PATH or note installation directory

2. **Clone and Setup**:
   ```bash
   git clone <your-repo>
   cd thisorthat
   pip install -r requirements.txt
   ```

3. **Run the Application**:
   ```bash
   python app.py
   ```

4. **Open in Browser**:
   - Navigate to `http://localhost:5000`

### Linux/Mac Installation

1. **Install Tesseract OCR**:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install tesseract-ocr
   
   # macOS
   brew install tesseract
   ```

2. **Setup Python Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Run the Application**:
   ```bash
   python app.py
   ```

## 🎯 How to Use

### Creating a Quiz

1. **Go to Admin Panel**: Click "Create New Quiz" on the homepage
2. **Choose Creation Method**:
   - **Upload Image**: Upload a "This or That" image and let OCR extract questions
   - **Manual Creation**: Create questions manually with the visual editor
3. **Fill in Details**: Add title and description
4. **Add Questions**: Each question has two options (left/right)
5. **Preview**: See how your questions will look with icons
6. **Create & Share**: Get a unique quiz ID to share with friends

### Playing a Quiz

1. **Start Playing**: Enter a quiz ID or browse available quizzes
2. **Swipe to Choose**: 
   - **Swipe Left** or **Click Left Arrow**: Choose the left option
   - **Swipe Right** or **Click Right Arrow**: Choose the right option
   - **Keyboard**: Use arrow keys for quick navigation
3. **Progress Tracking**: See your progress in real-time
4. **Share Results**: Share your completed quiz with friends

## 🏗️ Project Structure

```
thisorthat/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── templates/            # HTML templates
│   ├── base.html         # Base template with styling
│   ├── index.html        # Homepage
│   ├── admin.html        # Quiz creation interface
│   └── play.html         # Quiz playing interface
├── quizzes/              # Stored quiz JSON files
├── play_sessions/        # Active game sessions
└── uploads/              # Temporary image uploads
```

## 🎨 Design Features

- **Modern Gradient Design**: Beautiful purple-pink gradients throughout
- **Tinder-inspired Cards**: Swipeable cards with smooth animations
- **Smart Icon System**: Automatic icon assignment based on content
- **Responsive Layout**: Perfect on all screen sizes
- **Smooth Animations**: CSS transitions and JavaScript animations
- **Progress Visualization**: Real-time progress bars and counters

## 🔧 Technical Details

- **Backend**: Flask (Python)
- **Frontend**: Vanilla JavaScript + CSS3
- **Storage**: JSON files (no database required)
- **OCR**: Tesseract for image text extraction
- **Icons**: Font Awesome
- **Fonts**: Google Fonts (Poppins)

## 🎪 Icon System

The app automatically assigns relevant icons based on content:

- 🍕 **Food & Drink**: Pizza, burger, coffee, wine, etc.
- 🐱 **Animals**: Cat, dog, fish, bird, etc.
- 📱 **Technology**: Phone, laptop, tablet, games, etc.
- 🚗 **Transportation**: Car, bike, plane, train, etc.
- 🎬 **Entertainment**: Movies, music, books, TV, etc.
- ⚽ **Sports**: Football, basketball, tennis, etc.
- ☀️ **Weather**: Summer, winter, rain, snow, etc.

## 🚀 Deployment

For production deployment:

1. **Set Flask Environment**:
   ```bash
   export FLASK_ENV=production
   ```

2. **Use a Production Server**:
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:8000 app:app
   ```

3. **Configure Reverse Proxy** (nginx/Apache) for static files and SSL

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📝 License

This project is open source and available under the MIT License.

## 🐛 Troubleshooting

### Common Issues

1. **OCR Not Working**:
   - Ensure Tesseract is installed and in PATH
   - On Windows, you may need to set the tesseract path in the code

2. **Port Already in Use**:
   - Change the port in `app.py`: `app.run(port=5001)`

3. **File Permissions**:
   - Ensure write permissions for `quizzes/`, `play_sessions/`, and `uploads/` directories

## 🎉 Enjoy!

Start creating amazing "This or That" quizzes and share them with your friends! The intuitive Tinder-like interface makes it fun and engaging for everyone.

Happy swiping! 🎮✨ 