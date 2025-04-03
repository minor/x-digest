import os
import time
import re
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Add this import for finding elements by keys
from selenium.webdriver.common.keys import Keys

# Import common exceptions
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import google.generativeai as genai
import resend

# --- Configuration ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")  # (verified domain in Resend)
# Add X Credentials
X_USERNAME = os.getenv("X_USERNAME")
X_PASSWORD = os.getenv("X_PASSWORD")


if not all(
    [
        GEMINI_API_KEY,
        RESEND_API_KEY,
        RECIPIENT_EMAIL,
        SENDER_EMAIL,
        X_USERNAME,
        X_PASSWORD,
    ]
):
    print(
        "Error: Missing one or more environment variables (API keys, emails, or X credentials)."
    )
    exit()

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
# gemini_model = genai.GenerativeModel("gemini-2.0-flash") # great for longer amounts of tweets analyzed + faster responses
gemini_model = genai.GenerativeModel("gemini-2.5-pro-exp-03-25")

# Configure Resend
resend.api_key = RESEND_API_KEY

# --- Constants ---
X_LOGIN_URL = "https://x.com/login"
X_HOME_URL = "https://x.com/home"
SCROLL_PAUSE_TIME = 4  # Seconds to wait between scrolls
NUM_SCROLLS = 10  # How many times to scroll down the timeline
TARGET_TWEET_COUNT = 50
TWEET_SELECTOR = 'article[data-testid="tweet"]'  # Main selector for tweet elements
LOGIN_WAIT_TIMEOUT = 20  # Seconds to wait for login elements

# --- Helper Functions ---


def setup_driver():
    """Initializes and returns a Selenium WebDriver instance."""
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")  # Run headless later if needed
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )  # Mimic real browser
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)  # Wait up to 30 seconds for pages to load
        return driver
    except Exception as e:
        print(f"Error setting up WebDriver: {e}")
        print("Please ensure Chrome is installed and webdriver-manager can access it.")
        exit()


def login_to_x(driver, username, password):
    """Logs into X using provided credentials."""
    print(f"Navigating to {X_LOGIN_URL} for automated login...")
    driver.get(X_LOGIN_URL)

    try:
        # 1. Enter Username
        print("Entering username...")
        username_input = WebDriverWait(driver, LOGIN_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="text"]'))
            # Alternative selector if the above fails:
            # EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"]'))
        )
        username_input.send_keys(username)
        username_input.send_keys(
            Keys.RETURN
        )  # Often pressing Enter works like clicking Next

        # --- Optional: Explicitly click 'Next' if Enter doesn't work ---
        # try:
        #     next_button = WebDriverWait(driver, 5).until(
        #         EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Next')]"))
        #     )
        #     next_button.click()
        # except TimeoutException:
        #     print("Could not find 'Next' button, assuming Enter key worked.")
        # --------------------------------------------------------------

        # 2. Enter Password
        print("Entering password...")
        password_input = WebDriverWait(driver, LOGIN_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]'))
        )
        password_input.send_keys(password)
        password_input.send_keys(Keys.RETURN)  # Press Enter to log in

        # --- Optional: Explicitly click 'Log in' button ---
        # try:
        #     login_button = WebDriverWait(driver, 5).until(
        #         EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Log in')]"))
        #         # Alternative: (By.CSS_SELECTOR, 'div[data-testid="LoginForm_Login_Button"]')
        #     )
        #     login_button.click()
        # except TimeoutException:
        #      print("Could not find 'Log in' button, assuming Enter key worked.")
        # ----------------------------------------------------

        # 3. Verify Login Success (Wait for home timeline)
        print("Verifying login...")
        WebDriverWait(driver, LOGIN_WAIT_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div[aria-label*="Timeline"]')
            )
        )
        print("Login successful!")
        return True

    except TimeoutException:
        print(
            "Login failed: Timed out waiting for username/password field or timeline."
        )
        print("Possible reasons: Incorrect credentials, CAPTCHA, changed X UI.")
        # You might want to save a screenshot here for debugging
        # driver.save_screenshot("login_error.png")
        return False
    except NoSuchElementException:
        print("Login failed: Could not find a required login element.")
        print("The X login page structure might have changed.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during login: {e}")
        return False


def scrape_tweets(driver):
    """Scrolls the timeline and scrapes tweet data."""
    # No need to navigate again if login was successful, but check current URL just in case
    if X_HOME_URL not in driver.current_url:
        print(f"Not on the home timeline. Navigating to {X_HOME_URL}...")
        try:
            driver.get(X_HOME_URL)
            WebDriverWait(driver, LOGIN_WAIT_TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[aria-label*="Timeline"]')
                )
            )
        except Exception as e:
            print(f"Error navigating to home timeline after login attempt: {e}")
            return []
    else:
        print("Already on home timeline. Starting scroll and scrape...")

    scraped_tweets_data = []
    last_height = driver.execute_script("return document.body.scrollHeight")
    tweet_elements_found = set()  # To avoid duplicates from dynamic loading

    for i in range(NUM_SCROLLS):
        print(f"Scrolling down ({i + 1}/{NUM_SCROLLS})...")
        try:
            # Scroll down
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE_TIME)  # Wait for content to load

            # --- Scraping Logic ---
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")
            tweet_articles = soup.select(TWEET_SELECTOR)

            print(f"Found {len(tweet_articles)} potential tweet articles in view.")

            for article in tweet_articles:
                tweet_text_element = article.select_one('div[data-testid="tweetText"]')
                user_name_element = article.select_one('div[data-testid="User-Name"]')
                time_element = article.select_one(
                    "time[datetime]"
                )  # Find the time element
                permalink_element = (
                    time_element.find_parent("a") if time_element else None
                )  # Find its parent link

                tweet_text = (
                    tweet_text_element.get_text(strip=True)
                    if tweet_text_element
                    else None
                )

                author = None
                handle = None
                if user_name_element:
                    # Try to extract cleanly
                    name_span = user_name_element.select_one(
                        "span span"
                    )  # Often nested spans for name
                    handle_span = user_name_element.select_one(
                        'div[dir="ltr"] span'
                    )  # Look for the @handle specifically

                    if name_span:
                        author = name_span.get_text(strip=True)
                    if handle_span and handle_span.get_text(strip=True).startswith("@"):
                        handle = handle_span.get_text(strip=True)
                    # Fallback if specific spans not found
                    if not author and not handle:
                        author = user_name_element.get_text(
                            separator=" ", strip=True
                        )  # Less precise fallback

                tweet_link = None
                if permalink_element and permalink_element.has_attr("href"):
                    href = permalink_element["href"]
                    # Basic check if it looks like a status link
                    if "/status/" in href:
                        tweet_link = f"https://x.com{href}"

                # Use link as unique ID to avoid duplicates
                if tweet_text and tweet_link and tweet_link not in tweet_elements_found:
                    scraped_tweets_data.append(
                        {
                            "author": author or "Unknown Author",
                            "handle": handle or "",
                            "text": tweet_text,
                            "link": tweet_link,
                        }
                    )
                    tweet_elements_found.add(tweet_link)
                    print(f" Scraped: {handle or author}: {tweet_text[:50]}...")

            print(f"Total unique tweets scraped so far: {len(scraped_tweets_data)}")
            if len(scraped_tweets_data) >= TARGET_TWEET_COUNT:
                print("Reached target number of tweets.")
                break

            # Check if scroll height has changed, break if stuck
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                print(
                    "Scroll height didn't change, likely end of feed or loading issue."
                )
                break
            last_height = new_height

        except Exception as e:
            print(f"Error during scroll/scrape iteration {i + 1}: {e}")
            # You might want to continue to the next scroll attempt

    return scraped_tweets_data[:TARGET_TWEET_COUNT]  # Return up to the target count


def get_digest_from_llm(tweets):
    """Sends tweet text to Gemini and asks for a summarized digest."""
    print(f"Sending {len(tweets)} scraped tweets to Gemini for summarization...")
    if not tweets:
        return "No tweets were scraped successfully."

    # Prepare the text blob for the LLM
    tweet_blob = ""
    for i, tweet in enumerate(tweets):
        tweet_blob += f"Tweet {i + 1}:\n"
        tweet_blob += f"Author: {tweet['author']} ({tweet['handle']})\n"
        tweet_blob += f"Text: {tweet['text']}\n"
        tweet_blob += f"Link: {tweet['link']}\n\n"

    prompt = f"""hey, i have a bunch of tweets from my timeline that i've scraped very recently. could you pick the best 15 tweets that i would find interesting and give me a personalized daily "digest"? analyze these tweets and create a digest with the following EXACT format requirements:

1. start immediately with the first category (no introductory text)
2. use exactly these category headers in this order (skip any that have no relevant tweets):
   ### technology & science (ai/llms/biomed/quantum/space/real breakthroughs)
   ### world news (geopolitics, politics, u.s. news)
   ### finance & economics
   ### noteworthy 

3. under each category, list relevant tweets in this exact format (no numbers, they will be added automatically):
   @handle: [1-2 sentence summary] → <a href="[tweet url]" class="tweet-link">view on X</a>

4. do not include any other text, headers, or formatting

example of the exact format:
### technology & science
@handle: summary of the tweet goes here → <a href="https://x.com/status/123" class="tweet-link">view on X</a>
@another: another summary here → <a href="https://x.com/status/456" class="tweet-link">view on X</a>

### us news & politics
@handle: political summary here → <a href="https://x.com/status/789" class="tweet-link">view on X</a>

now, here are the tweets to analyze:

--- START OF TWEETS ---
{tweet_blob}
--- END OF TWEETS ---

now, generate the digest using the tweets above, making it feel conversational – complete sentences, natural flow, occasional wry commentary where appropriate. use lower cases. remember: start directly with "### Technology & Science" - no other text before it.
<final_digest>
"""

    try:
        response = gemini_model.generate_content(prompt)
        print("Gemini processing complete.")
        # Extract text after <final_digest> tag
        response_text = response.text
        if "<final_digest>" in response_text:
            response_text = response_text.split("<final_digest>")[1].strip()
        return response_text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return f"Error generating digest: {e}"


def format_html_email(digest_content):
    """Formats the digest content into a basic HTML email body."""
    print("Formatting HTML email...")

    # Get current date for the title
    current_date = time.strftime("%B %-d, %Y")

    # 1. Convert ### headers to styled div elements
    formatted_content = re.sub(
        r"^\s*###\s+(.*?)\s*$",
        r'<div class="category-header">\1</div>',
        digest_content,
        flags=re.MULTILINE,
    )

    # 2. Add hyperlinks to handles BEFORE wrapping in <li>
    # Looks for @handle: at the start of a line
    formatted_content = re.sub(
        r"^@([a-zA-Z0-9_]+):",  # Capture the handle
        # Replace with linked handle and the colon
        r'<a href="https://x.com/\1" target="_blank" class="handle-link">@\1</a>:',
        formatted_content,
        flags=re.MULTILINE,
    )

    # 3. Wrap each tweet line (now starting with linked handle) into a list item
    # This looks for lines starting with our link format and wraps the whole line
    # It assumes the summary and the 'view on X' link are on the same logical line from the LLM output
    formatted_content = re.sub(
        # Match line starting with <a href...> up to the next line break
        # or the end of the string
        r'^(<a href="https://x.com/.*?</a>:.*?)(?:\n|$)',
        # Wrap the matched line in <li> tags, preserving the newline/end
        r"<li class='tweet-item'>\1</li>\n",
        formatted_content,
        flags=re.MULTILINE,
    )
    # Clean up potential trailing newline added if the last line was a tweet
    formatted_content = formatted_content.strip()

    # 4. Wrap consecutive tweet items following a header in an ordered list
    # This regex looks for a category div followed immediately by one or more list items
    # It wraps *only the list items* in <ol> tags. DOTALL handles multi-line content within <li> if necessary.
    formatted_content = re.sub(
        r"(<div class=\"category-header\">.*?</div>\s*)((?:<li class='tweet-item'>.*?</li>\s*)+)",
        r"\1<ol class='tweet-list'>\n\2</ol>",  # Add newline for readability
        formatted_content,
        flags=re.DOTALL,  # Use DOTALL because <li> content might technically span lines
    )

    # 5. Handle any remaining double newlines as paragraph breaks (though likely fewer now)
    formatted_content = formatted_content.replace("\n\n", "<br><br>")

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>The X Digest</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #333;
            }}
            .container {{
                max-width: 700px;
                margin: 20px auto;
                padding: 20px;
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: #fff;
            }}
            h1 {{
                color: #1DA1F2; /* Twitter blue */
                font-size: 24px;
                margin-bottom: 16px;
            }}
            .category-header {{
                color: #000000;
                font-size: 16px;
                font-weight: 500;
                margin: 24px 0 12px 0;
                padding-bottom: 4px;
            }}
            .tweet-list {{
                list-style-type: disc;
                padding-left: 20px;
                margin: 15px 0;
                border-left: 2px solid #eee;
                background-color: #fdfdfd;
                border-radius: 4px;
                padding-top: 10px;
                padding-bottom: 1px;
            }}
            .tweet-item {{
                margin-bottom: 15px;
                padding-left: 3px;
                font-size: 14px;
                line-height: 1.5;
            }}
            a {{
                color: #1DA1F2;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .handle-link {{ /* Style for the handle link */
                /* font-weight: bold; */ /* Optionally make handle bold */
                 color: #14171A; /* Darker color for handle */
            }}
            .tweet-link {{ /* Style for the 'view on X' link */
                font-size: 0.9em;
                /* margin-left: 5px; */ /* Add space before the link */
            }}
            .intro-text {{
                font-size: 14px;
                color: #333;
                margin: 16px 0;
            }}
             hr {{
                border: none;
                border-top: 1px solid #eee;
                margin: 20px 0;
             }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>The X Digest — {current_date}</h1>
            <p class="intro-text">Here's your daily dose of what's happening, curated from your timeline. Buckle up!</p>
            <hr>
            {formatted_content}
            <hr>
            <p style="font-size: 0.8em; color: #777;">
                Generated by X Digest Bot. Remember that scraping can be unreliable.
            </p>
        </div>
    </body>
    </html>
    """
    # print(html_body) # Optional: print HTML for debugging
    return html_body


def send_email(html_content):
    """Sends the HTML email using the Resend API."""
    print(f"Sending email digest to {RECIPIENT_EMAIL}...")
    try:
        current_date = time.strftime("%B %-d, %Y")
        params = {
            "from": f"X Digest <{SENDER_EMAIL}>",
            "to": [RECIPIENT_EMAIL],
            "subject": f"Your Daily X Digest — {current_date}",
            "html": html_content,
        }
        email = resend.Emails.send(params)
        print(f"Email sent successfully! ID: {email['id']}")
        return True
    except Exception as e:
        print(f"Error sending email via Resend: {e}")
        # Check if the error response from Resend has more details
        if hasattr(e, "response") and e.response:
            try:
                error_details = e.response.json()
                print(f"Resend API Error Details: {error_details}")
            except ValueError:  # If response is not JSON
                print(f"Resend API Raw Error Response: {e.response.text}")
        return False


# --- Main Execution ---
if __name__ == "__main__":
    driver = None  # Initialize driver to None
    try:
        driver = setup_driver()

        # --- Automated Login Step ---
        login_successful = login_to_x(driver, X_USERNAME, X_PASSWORD)

        if not login_successful:
            print("Exiting script due to login failure.")
            exit()  # Exit if login fails

        # --- Scrape Tweets ---
        scraped_tweets = scrape_tweets(driver)

        if not scraped_tweets:
            print("No tweets were scraped. Exiting.")
            exit()

        print(f"\nSuccessfully scraped {len(scraped_tweets)} unique tweets.")

        # --- Get LLM Digest ---
        digest = get_digest_from_llm(scraped_tweets)

        if "Error:" in digest:
            print(f"Failed to generate digest: {digest}")
            exit()

        print("\n--- Generated Digest ---")
        print(digest)
        print("--- End of Digest ---\n")

        # --- Format and Send Email ---
        html_email_body = format_html_email(digest)
        send_email(html_email_body)

    except Exception as e:
        print(f"\nAn unexpected error occurred in the main script: {e}")
    finally:
        if driver:
            print("Closing browser...")
            driver.quit()
        print("Script finished.")
