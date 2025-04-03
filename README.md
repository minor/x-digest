# x-digest: your personalized X digest

tired of endless scrolling but still want to stay informed? `x-digest` delivers a daily summary of your favorite X tweets directly to your inbox. this script automates the process of scraping, summarizing, and emailing a personalized digest of your timeline.

## features

- **automated scraping:** efficiently scrapes tweets from your X timeline using selenium
- **intelligent summarization:** leverages google's gemini 2.5-pro-thinking to summarize and categorize tweets into a concise digest
- **customizable categories:** organizes tweets into relevant categories like technology, world news, finance, and noteworthy mentions
- **email delivery:** sends the digest directly to your email using the resend api
- **two modes:**
  - **manual login (`x_digest_manual.py`):** requires manual login to X in the browser
  - **autonomous login (`x_digest_autonomous.py`):** automates the login process using your X credentials

## prerequisites

- **python >=3.6+**
- **chrome browser**
- **environment variables:**

  ```plaintext
  # api keys
  GEMINI_API_KEY=           # your google gemini api key
  RESEND_API_KEY=           # your resend api key for sending emails

  # email configuration
  RECIPIENT_EMAIL=          # where you want to receive the digest
  SENDER_EMAIL=             # verified sender email in resend (e.g., digest@yourdomain.com)

  # X credentials (only for autonomous login)
  X_USERNAME=               # your X username or email
  X_PASSWORD=               # your X account password
  ```

## installation

1.  **clone the repository:**

    ```bash
    git clone https://github.com/minor/x-digest.git
    cd x-digest
    ```

2.  **install dependencies:**

    ```bash
    pip install selenium webdriver-manager beautifulsoup4 google-generativeai python-dotenv resend
    ```

3.  **set up environment variables:**
    - create a `.env` file in the project's root directory
    - add your credentials using the format shown in the prerequisites section

## usage

### manual login (`x_digest_manual.py`)

1.  run the script:

    ```bash
    python x_digest_manual.py
    ```

2.  a chrome browser window will open, and you will be prompted to manually log in to your X account
3.  after successful login, press enter in the terminal to continue the script

### autonomous login (`x_digest_autonomous.py`)

1.  ensure you have set `X_USERNAME` and `X_PASSWORD` in your `.env` file
2.  run the script:

    ```bash
    python x_digest_autonomous.py
    ```

## script details

### `x_digest_manual.py`

- requires manual login to X in the browser
- scrapes tweets from your timeline, summarizes them using gemini, and sends the digest via email

### `x_digest_autonomous.py`

- automates the login process using your X credentials
- includes robust error handling for login failures and scraping issues
- uses selenium to navigate and scrape the X timeline

## disclaimer

this script is for **educational purposes only**. please note:

- automated login and scraping likely violate X's terms of service. use at your own risk.
- this project is not affiliated with, endorsed by, or sponsored by X
