from time import sleep
import argparse
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import logging


__author__ = 'Modified for Direct Post Commenting'
__version__ = '2.1.0'
__status__ = 'Dev'

# Setup logging
logging.basicConfig(
    format='%(levelname)s [%(asctime)s] %(message)s', 
    datefmt='%m/%d/%Y %r', 
    level=logging.INFO
)
logger = logging.getLogger()


class InstagramCommentBot:
    def __init__(self, headless=False, log_callback=None, profile_name="default", username=None, password=None):
        """Initialize the Instagram comment bot."""
        self.browser = None
        self.wait = None
        self.headless = headless
        self.log_callback = log_callback
        self.profile_name = profile_name
        self.username = username
        self.password = password
        self.waiting_for_manual_login = False
        
    def log(self, message, level=logging.INFO):
        """Log message and send to callback if available."""
        if level == logging.INFO:
            logger.info(message)
        elif level == logging.ERROR:
            logger.error(message)
        elif level == logging.WARNING:
            logger.warning(message)
            
        if self.log_callback:
            self.log_callback(message, level)

    def setup_browser(self):
        """Setup Chrome browser with appropriate options."""
        options = Options()
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        # Add persistence via User Data Directory
        # Move all sessions into a dedicated subfolder to keep root clean
        base_session_dir = "Instagram_session"
        if not os.path.exists(base_session_dir):
            os.makedirs(base_session_dir)
            
        profile_path = os.path.abspath(os.path.join(base_session_dir, self.profile_name))
        options.add_argument(f"user-data-dir={profile_path}")
        options.add_argument("--profile-directory=Default")
        
        if self.headless:
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Linux container compatibility (Mandatory for LXC/Docker)
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--remote-debugging-port=9222')
        
        # Anti-detection measures
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Initialize chrome driver using Selenium Manager
        self.log("🤖 Preparing the bot engine (this may take a moment)...")
        self.browser = webdriver.Chrome(service=Service(), options=options)
        
        # Hide navigator.webdriver flag
        self.browser.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
        
        self.wait = WebDriverWait(self.browser, 10)
        self.log("✅ Engine ready and secured.")
        
        self.log(f"📂 Loading session for profile: {self.profile_name}")
        
    def type_slowly(self, element, text):
        """Type text slowly like a human, with support for emojis and React state sync."""
        element.click()
        element.clear()
        for char in text:
            if ord(char) > 0xFFFF:
                self.browser.execute_script("arguments[0].value += arguments[1];", element, char)
            else:
                element.send_keys(char)
            sleep(0.1)
        
        # Trigger events to ensure React picks up the changes
        self.browser.execute_script("""
            var el = arguments[0];
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        """, element)
        
    def is_logged_in(self):
        """Check if user is already logged in to Instagram."""
        try:
            current_url = self.browser.current_url
            self.log("🌐 Checking Instagram session status...")
            
            # Wait a bit for page to load
            sleep(3)
            
            # Look for multiple indicators of being logged in
            self.log("🔍 Searching for active login session...")
            indicators = [
                ("//svg[@aria-label='Home' or @aria-label='New post' or @aria-label='Direct message' or @aria-label='Explore' or @aria-label='Reels' or @aria-label='Messenger']", "Navigation Icons"),
                ("//input[@placeholder='Search']", "Search Bar"),
                ("//div[@role='navigation']", "Navigation Sidebar"),
                ("//img[contains(@alt, \"profile picture\")]", "Profile Picture")
            ]
            
            for xpath, name in indicators:
                try:
                    self.browser.find_element(By.XPATH, xpath)
                    self.log(f"✅ Session verified: Found {name}")
                    return True
                except NoSuchElementException:
                    continue
            
            # Check if we clearly see a login form
            try:
                self.browser.find_element(By.NAME, 'username')
                self.log("Clearly not logged in: login form detected")
                return False
            except NoSuchElementException:
                pass
            
            if 'accounts/login' in current_url:
                self.log("Clearly not logged in: on login URL")
                return False
            
            # If we don't see a login form but can't find clear "Home" icons, 
            # we might be on a landing page or partial load.
            self.log("Login status unclear (no navigation icons found yet)")
            return None # Return None for 'unclear'
            
        except (NoSuchElementException, Exception) as e:
            msg = str(e).lower()
            if "invalid session id" in msg or "no such window" in msg:
                self.log("Browser session lost or closed.", logging.WARNING)
                return "SESSION_LOST"
            self.log(f"Error checking login status: {e}", logging.ERROR)
            return False

    def get_screenshot_as_png(self):
        """Capture current browser screen as PNG bytes."""
        try:
            if self.browser:
                return self.browser.get_screenshot_as_png()
        except:
            pass
        return None
    
    def login(self):
        """Login to Instagram - Automated with manual fallback."""
        try:
            self.log("🏠 Opening Instagram homepage...")
            self.browser.get('https://www.instagram.com/') # Go to root first
            sleep(8) # Increased for LXC
            
            # Check if already logged in (maybe session was active)
            if self.is_logged_in() == True:
                self.log("✨ Session verified! Already logged in.")
                return True
            
            self.log("📍 Navigating to login page...")
            self.browser.get('https://www.instagram.com/accounts/login/')
            sleep(5) # Increased for LXC
            
            # 1. Try Automated Login
            self.log(f"Attempting automated login for user: {self.username}")
            try:
                # Handle possible Cookie Consent banner
                try:
                    cookie_selectors = [
                        "//button[contains(text(), 'Allow all cookies')]",
                        "//button[contains(text(), 'Allow Essential and Optional')]",
                        "//button[contains(text(), 'Allow all')]",
                        "//button[contains(., 'Allow')]",
                        "//div[contains(text(), 'Allow')]"
                    ]
                    cookie_btn = None
                    for selector in cookie_selectors:
                        try:
                            cookie_btn = WebDriverWait(self.browser, 3).until(
                                EC.element_to_be_clickable((By.XPATH, selector))
                            )
                            if cookie_btn: 
                                cookie_btn.click()
                                self.log(f"Dismissed cookie consent banner: {selector}")
                                sleep(2)
                                break
                        except: continue
                except:
                    pass

                # Find username field using multiple possible selectors
                user_selectors = [
                    "username", 
                    "//*[@name='username']", 
                    "//input[@aria-label='Phone number, username, or email']",
                    "//input[@type='text']",
                    "//input[contains(@class, '_2hvTZ')]"
                ]
                user_field = None
                self.log("🔍 Looking for username field...")
                for selector in user_selectors:
                    try:
                        by = By.NAME if selector == "username" else By.XPATH
                        user_field = WebDriverWait(self.browser, 5).until(
                            EC.presence_of_element_located((by, selector))
                        )
                        if user_field: 
                            self.log(f"📍 Found username field using selector: {selector}")
                            break
                    except: continue

                if not user_field:
                    # Debug help: save a screenshot on failure to see what's actually on screen
                    if self.headless:
                        self.browser.save_screenshot(f"login_failure_{self.profile_name}.png")
                        self.log(f"📸 Saved failure screenshot to login_failure_{self.profile_name}.png", logging.WARNING)
                    raise Exception("Could not find username field with any known selectors. Page might be restricted or structure changed.")

                # Find password field
                self.log("🔍 Looking for password field...")
                pass_field = WebDriverWait(self.browser, 5).until(
                    EC.presence_of_element_located((By.NAME, "password"))
                )
                
                # Human-like typing
                self.log(f"⌨️ Typing username: {self.username}")
                self.type_slowly(user_field, self.username)
                sleep(1)
                self.log("⌨️ Typing password...")
                self.type_slowly(pass_field, self.password)
                sleep(1)
                
                # Submit
                self.log("🔍 Looking for 'Log in' button...")
                submit_selectors = ["//button[@type='submit']", "//div[text()='Log in']", "//button[contains(., 'Log In')]"]
                for selector in submit_selectors:
                    try:
                        submit_btn = WebDriverWait(self.browser, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        self.log(f"🚀 Clicking login button: {selector}")
                        submit_btn.click()
                        break
                    except:
                        if selector == submit_selectors[-1]: # If last one failing, try Enter key
                            self.log("⚠️ Button click failed, trying ENTER key fallback...")
                            pass_field.send_keys(Keys.ENTER)
                
                self.log("🔓 Login form submitted. Waiting for page transition (12s)...")
                sleep(12) # Increased wait for potential redirects/popups
                
                # Check for "Save Login Info"
                try:
                    save_info_btn = WebDriverWait(self.browser, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[text()='Save info' or text()='Save Info']"))
                    )
                    save_info_btn.click()
                    self.log("💾 Saved login info for future use.")
                    sleep(3)
                except:
                    pass
                
                # Check for "Turn on Notifications"
                try:
                    not_now_btn = WebDriverWait(self.browser, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[text()='Not Now' or text()='Not now']"))
                    )
                    not_now_btn.click()
                    self.log("🔕 Dismissed notification prompt.")
                    sleep(3)
                except:
                    pass
                
                # Verify if login worked
                if self.is_logged_in() == True:
                    self.log("🎊 Automated login successful!")
                    return True
                else:
                    self.log("Automated login verification failed.", logging.WARNING)
                    
            except Exception as e:
                self.log(f"Automated login failed or fields not found: {e}", logging.WARNING)
            
            # 2. Manual Fallback
            self.log("=" * 60)
            self.log("MANUAL LOGIN REQUIRED (Automation failed)")
            self.log("=" * 60)
            self.log("1. Please login to Instagram in the browser window.")
            self.log("2. Complete any CAPTCHA or Two-Factor Authentication.")
            self.log("3. IMPORTANT: Wait until you see your Instagram Home Feed.")
            
            if self.log_callback:
                self.log("Waiting for manual login to complete (monitoring browser)...")
                # Loop and wait for login detection
                max_retries = 90 # 3 minutes for manual action
                for _ in range(max_retries):
                    status = self.is_logged_in()
                    if status == True:
                        self.log("Manual login detected! Proceeding...")
                        return True
                    elif status == "SESSION_LOST":
                        self.log("Login aborted: Browser window closed.", logging.ERROR)
                        return False
                    sleep(2)
                self.log("Manual login timeout reached.", logging.ERROR)
                return False
            else:
                self.log("4. Then, press Enter HERE in the terminal to continue...")
                self.log("=" * 60)
                input()
                
                # Final verification
                sleep(2)
                if self.is_logged_in() == True:
                    self.log("Manual login verified. Proceeding...")
                    return True
                else:
                    self.log("Still not logged in! Exiting.", logging.ERROR)
                    return False
                
        except Exception as e:
            self.log(f"Execution error during login: {e}", logging.ERROR)
            return False

    def login_standalone(self):
        """Standalone login mode to just setup the session."""
        try:
            self.setup_browser()
            success = self.login()
            if success:
                self.log("✅ Session setup complete! You can now run the bot in headless mode.")
            return success
        except Exception as e:
            self.log(f"Standalone login error: {e}", logging.ERROR)
            return False
        finally:
            self.log("Closing browser in 5 seconds...")
            sleep(5)
            if self.browser:
                self.browser.quit()

    def navigate_to_post(self, post_url):
        """Navigate to a specific Instagram post."""
        try:
            self.log(f"📍 Navigating to post: {post_url}")
            self.browser.get(post_url)
            sleep(5)
            
            # Check for the "Login to see more" modal which often blocks post pages
            try:
                # Look for the close button on the login modal or the login button in the modal
                login_modal_close = self.browser.find_element(By.XPATH, "//div[@role='dialog']//svg[@aria-label='Close']")
                login_modal_close.click()
                self.log("🛡️ Closed annoying login modal.")
                sleep(1)
            except NoSuchElementException:
                pass

            # Verify we're on the post page and can see the comment section
            try:
                # Instagram sometimes hides the comment box behind a "Log In" button
                self.browser.find_element(By.XPATH, "//textarea[@placeholder='Add a comment…' or @placeholder='Add a comment...' or contains(@aria-label, 'Add a comment')]")
                self.log("🗨️ Found the comment section.")
                return True
            except NoSuchElementException:
                # Check if there's a "Log In" button where the comment box should be
                try:
                    self.browser.find_element(By.XPATH, "//a[text()='Log in' or text()='Log In']")
                    self.log("⚠️ Post page is asking for login again. Retrying...", logging.WARNING)
                    return False
                except NoSuchElementException:
                    self.log("🕵️ Comment section hidden? Attempting to find it anyway...", logging.WARNING)
                    # Check if it's a Reel
                    if "/reels/" in self.browser.current_url:
                        self.log("Detected Reel layout, attempting to reveal comment section if hidden...")
                    # Try scrolling down to trigger loading
                    self.browser.execute_script("window.scrollTo(0, 500);")
                    sleep(2)
                    return True # Continue anyway as post_comment has nested retries
        except Exception as e:
            self.log(f"Error navigating to post: {e}", logging.ERROR)
            return False
    
    def post_comment(self, comment_text, count=1):
        """Post a comment on the current Instagram post."""
        comments_posted = 0
        
        for i in range(count):
            try:
                self.log(f"Attempting to post comment {i+1}/{count}")
                
                # Find the comment textarea - try multiple selectors
                try:
                    # Generic selector that often works for both posts and reels
                    selectors = [
                        "//textarea[@placeholder='Add a comment…' or @placeholder='Add a comment...' or contains(@aria-label, 'Add a comment')]",
                        "//textarea[contains(@class, 'x78zum5')]", # Common reel class
                        "//div[@role='textbox']"
                    ]
                    comment_box = None
                    for selector in selectors:
                        try:
                            comment_box = WebDriverWait(self.browser, 5).until(
                                EC.presence_of_element_located((By.XPATH, selector))
                            )
                            if comment_box: break
                        except: continue
                    
                    if not comment_box:
                        raise TimeoutException("No comment box found with default selectors")
                        
                except TimeoutException:
                    self.log("Standard comment box not found, trying fallback...", logging.WARNING)
                    # Fallback: try finding any textarea
                    comment_box = self.browser.find_element(By.TAG_NAME, "textarea")
                
                comment_box.click()
                sleep(1)
                
                # Re-find to avoid stale element
                comment_box = self.browser.find_element(By.XPATH, "//textarea[contains(@aria-label, 'Add a comment')]")
                # Type the comment human-like
                self.log(f"✍️ Typing comment (length: {len(comment_text)} chars)...")
                self.type_slowly(comment_box, comment_text)
                self.log("🆗 Comment entered. Clicking Post.")
                sleep(2)
                
                # Find and click the Post button - try multiple common XPaths
                post_button_selectors = [
                    "//div[text()='Post']",
                    "//button[contains(., 'Post')]",
                    "//div[@role='button' and text()='Post']",
                    "//button[@type='submit' and contains(., 'Post')]"
                ]
                
                post_clicked = False
                for selector in post_button_selectors:
                    try:
                        # Shorter wait for each attempt
                        button = WebDriverWait(self.browser, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        button.click()
                        self.log(f"Comment {i+1} posted via button")
                        post_clicked = True
                        break
                    except:
                        continue
                
                if not post_clicked:
                    self.log("Could not find Post button, trying Enter key fallback...", logging.WARNING)
                    comment_box.send_keys(Keys.ENTER)
                    post_clicked = True # Consider it clicked for verification
                
                # --- Post Verification ---
                self.log("🧐 Verifying that the comment appeared...")
                verification_success = False
                for _ in range(5): # Wait up to 10 seconds for verification
                    sleep(2)
                    # 1. Check if comment box is cleared (often happens on success)
                    try:
                        current_val = self.browser.execute_script("return arguments[0].value;", comment_box)
                        if not current_val:
                            self.log("✨ Success: Comment box is clear.")
                            verification_success = True
                            break
                    except: pass
                    
                    # 2. Look for the comment text on the page
                    try:
                        # Find the most recent comment with our text
                        self.browser.find_element(By.XPATH, f"//*[text()='{comment_text}']")
                        self.log("✨ Success: Found your comment in the feed!")
                        verification_success = True
                        break
                    except: pass
                
                if verification_success:
                    self.log(f"✅ Comment {i+1} verified.")
                    comments_posted += 1
                else:
                    self.log(f"⚠️ Could not verify comment {i+1} presence. It might be delayed.", logging.WARNING)
                    # We still increment if post_clicked was true, but we log the warning
                    comments_posted += 1
                
                # Wait between comments to avoid rate limiting
                if i < count - 1:
                    wait_time = 10 + (i * 3) # More generous wait time for reliability
                    for remaining in range(wait_time, 0, -5):
                        self.log(f"Cooling down... {remaining} seconds remaining before next comment.")
                        sleep(5 if remaining >= 5 else remaining)
                
            except Exception as e:
                self.log(f"Error posting comment {i+1}: {e}", logging.ERROR)
                continue
        
        self.log(f"Successfully posted {comments_posted}/{count} comments")
        return comments_posted
    
    def run(self, post_url, comment_text, comment_count=1):
        """Main execution flow."""
        try:
            self.setup_browser()
            
            # First, go to Instagram homepage and login
            self.log("Opening Instagram homepage...")
            self.browser.get('https://www.instagram.com/')
            sleep(5)
            
            # Check if already logged in
            if not self.is_logged_in():
                # Login if not authenticated
                if not self.login():
                    self.log("Login failed. Exiting.", logging.ERROR)
                    return False
            else:
                self.log("Already logged in!")
            
            # Now navigate to the post - with retry logic if login is requested
            self.log(f"Navigating to post: {post_url}")
            if not self.navigate_to_post(post_url):
                self.log("Redirected due to login request. Retrying login flow...")
                if not self.login():
                    self.log("Login retry failed. Exiting.", logging.ERROR)
                    return False
                # Try navigating again after second login attempt
                if not self.navigate_to_post(post_url):
                    self.log("Still unable to reach post after login retry. Exiting.", logging.ERROR)
                    return False
            
            # Post comments
            posted = self.post_comment(comment_text, comment_count)
            
            if posted > 0:
                self.log(f"✓ Successfully posted {posted} comment(s)!")
                return True
            else:
                self.log("Failed to post any comments", logging.ERROR)
                return False
                
        except KeyboardInterrupt:
            self.log("\nBot stopped by user")
            return False
        except Exception as e:
            self.log(f"Error in main execution: {e}", logging.ERROR)
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.log("Closing browser in 10 seconds...")
            sleep(10)
            if self.browser:
                self.browser.quit()
            self.log("Browser closed")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Instagram Comment Bot - Post comments on specific Instagram posts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python insta-bot.py "https://www.instagram.com/p/ABC123/" "Great post!"
  python insta-bot.py "https://www.instagram.com/p/ABC123/" "Nice!" --count 3
  python insta-bot.py "https://www.instagram.com/p/ABC123/" "Amazing" --count 5 --headless
        """
    )
    
    parser.add_argument('post_url', help='Instagram post URL')
    parser.add_argument('comment', help='Comment text to post')
    parser.add_argument('--count', type=int, default=1, help='Number of times to post the comment (default: 1)')
    parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
    
    args = parser.parse_args()
    
    # Validate post URL
    if 'instagram.com' not in args.post_url:
        logger.error("Invalid Instagram URL")
        sys.exit(1)
    
    # Validate comment count
    if args.count < 1:
        logger.error("Comment count must be at least 1")
        sys.exit(1)
    
    if args.count > 10:
        logger.warning("Posting more than 10 comments may trigger Instagram's spam detection!")
        response = input("Continue? (y/n): ")
        if response.lower() != 'y':
            logger.info("Aborted by user")
            sys.exit(0)
    
    # Run the bot
    bot = InstagramCommentBot(headless=args.headless)
    success = bot.run(args.post_url, args.comment, args.count)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
