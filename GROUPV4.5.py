import secrets
import time
from collections import deque
from flask import Flask, render_template_string, request, Response, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import base64
import io
import re
import datetime
import json
import logging
import sys
import os
import random
import string
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logging.getLogger('werkzeug').setLevel(logging.CRITICAL)

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app, async_mode='threading')

messages = []
nextid = 1
creds = {}
userdata = {}
nextguest = 1
dms = {}

groups = {}
clientstate = {}
sockets = {}
calls = {}

MAXBYTES = 1 * 1024 * 1024
MAXVOICE = 60

ipreqs = {}
REQLIMIT = 1000
REQWINDOW = 300

BOT = "SystemBot"
SPAMCOUNT = 10
SPAMWINDOW = 1.5
spamtimestamps = {}

BANNEDWORDS = {
    'anal', 'anus', 'arse', 'ass', 'asshole', 'bitch', 'blowjob', 'boner',
    'butt', 'clit', 'cock', 'cunt', 'dick', 'dildo', 'dyke', 'fag',
    'faggot', 'fellatio', 'fuck', 'fucker', 'fucking', 'genitals', 'handjob',
    'homo', 'jerkoff', 'jizz', 'kike', 'labia', 'muff', 'nigger', 'nigga',
    'orgasm', 'penis', 'piss', 'poop', 'porn', 'pussy', 'rape', 'rectum',
    'scrotum', 'sex', 'shit', 'slut', 'smegma', 'snatch', 'sperm', 'spunk',
    'squirt', 'tits', 'vagina', 'vulva', 'wank', 'whore'
}

EMOJIS = ['👍', '❤️', '😂', '😯', '😢', '😡', '👌', '🤔', '🔥', '🎉']

LOGINHTML = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Login - Localhost Chat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: linear-gradient(45deg, rgba(128, 128, 128, 0.6), rgba(255, 0, 0, 0.4)), #2c2c2c;
            background-size: 400% 400%;
            animation: gradientBG 15s ease infinite;
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
        }
        @keyframes gradientBG {
            0%{background-position:0% 50%}
            50%{background-position:100% 50%}
            100%{background-position:0% 50%}
        }
        .login-container {
            background-color: rgba(80, 80, 80, 0.85);
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            width: 90%;
            max-width: 400px;
            text-align: center;
            color: #e0e0e0;
        }
        h2 {
            margin-bottom: 25px;
        }
        .input-group {
            margin-bottom: 20px;
            text-align: left;
        }
        .input-group label {
            display: block;
            margin-bottom: 5px;
            font-size: 0.9em;
        }
        .input-group input {
            width: 100%;
            padding: 10px;
            border-radius: 5px;
            border: 1px solid #777;
            background-color: #666;
            color: #fff;
            box-sizing: border-box;
        }
        .input-group input::placeholder {
            color: #bbb;
        }
        .button {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 5px;
            background-color: #7d4ba8;
            color: white;
            font-size: 1em;
            cursor: pointer;
            transition: background-color 0.3s;
        }
        .button:hover {
            background-color: #5e3881;
        }
        .footer-link {
            margin-top: 20px;
            font-size: 0.9em;
        }
        .footer-link a {
            color: #a0cfff;
            text-decoration: none;
        }
        .footer-link a:hover {
            text-decoration: underline;
        }
        .error {
            color: #ff8a8a;
            margin-bottom: 15px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>{{ "Login" if is_login else "Register" }}</h2>
        {% if error %}
            <p class="error">{{ error }}</p>
        {% endif %}
        <form method="post">
            <div class="input-group">
                <label for="username">Username</label>
                <input type="text" name="username" id="username" required>
            </div>
            <div class="input-group">
                <label for="password">Password</label>
                <input type="password" name="password" id="password" required>
            </div>
            <div class="input-group">
                <label for="captcha">{{ captcha_question }}</label>
                <input type="number" name="captcha" id="captcha" required>
            </div>
            <button type="submit" class="button">{{ "Login" if is_login else "Register" }}</button>
        </form>
        <div class="footer-link">
            {% if is_login %}
                Don't have an account? <a href="/register">Register here</a>
            {% else %}
                Already have an account? <a href="/login">Login here</a>
            {% endif %}
        </div>
         <p style="font-size: 0.8em; color: #ccc; margin-top: 20px;">
            <b>Important:</b> All data including messages, groups, polls, and files are stored only in server memory. Everything will be permanently lost when the server restarts.
        </p>
    </div>
</body>
</html>
"""

INDEXHTML = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Localhost Chat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="/style.css?v={cache_buster}">
</head>
<body>
    <div id="chat-window">
        <div id="header">
            <span id="chat-title">Chat Room</span>
            <input type="search" id="message-search-input" placeholder="Search loaded messages...">
            <div class="header-right-controls">
                <button id="online-users-button">Online</button>
                <button id="dms-button">DMs</button>
                <button id="global-chat-button" style="display: none;">Global Chat</button>
                <div id="joined-groups-container"></div>
                <button id="your-group-button" style="display: none;">Your group👥</button>
                <button id="create-group-button">Create Group</button>
                <button id="settings-button">Settings</button>
                <div id="settings-dropdown" class="dropdown-content">
                    <label>
                        Message Filter:
                        <input type="checkbox" id="message-filter-toggle">
                        <span class="filter-description">Hide inappropriate words.</span>
                    </label>
                     <label>
                        Dark theme:
                        <input type="checkbox" id="dark-theme-toggle">
                        <span class="filter-description">Use dark interface colors.</span>
                    </label>
                     <label>
                        Light theme:
                        <input type="checkbox" id="light-theme-toggle">
                        <span class="filter-description">Use light interface colors.</span>
                    </label>
                    <label>
                        Notifications:
                        <input type="checkbox" id="notifications-toggle">
                        <span class="filter-description">Show desktop notifications.</span>
                    </label>
                    <a href="/logout" id="logout-button">Logout</a>
                </div>
            </div>
        </div>
        <div id="group-info-bar" style="display: none;">
            <span id="group-name-display"></span> |
            Members: <span id="member-count-display">0</span> |
            Channels: <span id="channel-list-display"></span>
            <button id="create-channel-button" style="display: none; margin-left: 10px;">Create Channel</button>
            <button id="copy-group-url-button" style="display: none; margin-left: 10px;">Copy URL</button>
        </div>
        <div id="messages"></div>
        <div id="typing-indicator"></div>
        <div id="input-area">
            <div id="mention-suggestions"></div>
            <div id="replying-to-indicator" style="display: none;"></div>
            <input type="text" id="message-input" placeholder="Type your message...">
            <input type="file" id="image-file-input" accept="image/*" style="display: none;">
            <input type="file" id="generic-file-input" accept="*/*" style="display: none;">
            <div class="button-row">
                 <button id="attach-image-button">Attach Image</button>
                 <button id="attach-file-button">Attach File</button>
                 <button id="record-voice-button">Record Voice</button>
                 <button id="poll-button">Poll</button>
            </div>
            <div id="staged-files-indicator"></div>
            <button id="send-button">Send</button>
        </div>
    </div>
    <div id="image-modal" class="modal">
      <span class="modal-close">×</span>
      <img class="modal-content" id="modal-image">
      <button id="modal-download-button">Download</button>
    </div>
    <div id="reaction-picker" class="reaction-picker" style="display: none;"></div>

    <div id="online-users-panel" class="side-panel">
        <button class="close-panel-btn">×</button>
        <h3>Online Users</h3>
        <ul id="online-users-list"></ul>
    </div>
    
    <div id="dms-panel" class="modal">
      <div class="dms-content">
        <span class="dms-close-btn">×</span>
        <div id="dms-container">
            <div id="dms-list-panel">
                <h3>Conversations</h3>
                <ul id="dms-conversations-list"></ul>
            </div>
            <div id="dms-chat-panel">
                <div id="dm-chat-header">Select a conversation</div>
                <div id="dm-messages"></div>
                <div id="dm-input-area" style="display: none;">
                     <input type="text" id="dm-message-input" placeholder="Type a DM...">
                     <button id="dm-call-button">📞 Call</button>
                     <button id="send-dm-button">Send</button>
                </div>
            </div>
        </div>
       </div>
    </div>
    
    <div id="poll-creation-modal" class="modal">
        <div class="modal-content-form">
            <span class="modal-close poll-modal-close">×</span>
            <h3>Create a Poll</h3>
            <form id="poll-form">
                <input type="text" id="poll-question" placeholder="Poll Question" required maxlength="256">
                <input type="text" class="poll-option" placeholder="Option 1" required maxlength="100">
                <input type="text" class="poll-option" placeholder="Option 2" required maxlength="100">
                <div id="poll-additional-options"></div>
                <button type="button" id="add-poll-option-btn">Add Option</button>
                <button type="submit">Create Poll</button>
            </form>
        </div>
    </div>
    
    <div id="call-ui" class="modal">
        <div class="call-container">
            <video id="remote-video" autoplay playsinline></video>
            <video id="local-video" autoplay playsinline muted></video>
            <div id="call-info"></div>
            <div class="call-controls">
                <button id="toggle-mic-btn">Mute</button>
                <button id="toggle-camera-btn">Cam Off</button>
                <button id="flip-camera-btn">Flip Cam</button>
                <button id="end-call-btn">End Call</button>
            </div>
        </div>
    </div>
    
    <div id="incoming-call-modal" class="modal">
      <div class="modal-content-form">
        <h3 id="incoming-call-text">Incoming Call...</h3>
        <button id="accept-call-btn">Accept</button>
        <button id="decline-call-btn">Decline</button>
      </div>
    </div>


    <script>
        const GROUPID = {groupidjson};
        const CHANNELID = {channelidjson};
        const EMOJIS = {emojisjson};
    </script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script src="/script.js?v={cache_buster}"></script>
</body>
</html>
"""

STYLECSS = r"""
body {
    font-family: sans-serif;
    margin: 0;
    padding: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    background-color: #444444;
    color: #e0e0e0;
    transition: background-color 0.3s ease;
}

.light-mode body {
    background-color: #f0f0f0;
    color: #333;
}

#chat-window {
    width: 95%;
    max-width: 800px;
    height: 95vh;
    border: 1px solid #222;
    display: flex;
    flex-direction: column;
    background-color: #505050;
    box-shadow: 0 0 20px rgba(0, 0, 0, 0.6);
    border-radius: 8px;
    overflow: hidden;
    transition: background-color 0.3s ease, box-shadow 0.3s ease;
}

.light-mode #chat-window {
    background-color: #fff;
    border-color: #ccc;
    box-shadow: 0 0 20px rgba(0, 0, 0, 0.2);
}

#header {
    padding: 10px 15px;
    background-color: #404040;
    color: #fff;
    font-size: 1.2em;
    font-weight: bold;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: relative;
    transition: background-color 0.3s ease;
}
.light-mode #header {
    background-color: #e0e0e0;
    color: #333;
}
#message-search-input {
    padding: 4px 8px;
    border-radius: 10px;
    border: 1px solid #777;
    background-color: #666;
    color: #fff;
    font-size: 0.8em;
    margin-left: 15px;
    margin-right: auto;
}
.light-mode #message-search-input {
    background-color: #fff;
    border-color: #ccc;
    color: #333;
}

.header-right-controls {
    display: flex;
    align-items: center;
    gap: 10px;
    position: relative;
}
.header-right-controls button {
    background-color: #5cb85c;
    color: white;
    padding: 5px 10px;
    border: none;
    border-radius: 4px;
    font-size: 0.9em;
    cursor: pointer;
    transition: background-color 0.2s ease;
}
.header-right-controls button:hover {
    background-color: #4cae4c;
}

#dms-button { background-color: #5bc0de; }
#dms-button:hover { background-color: #31b0d5; }

#your-group-button { background-color: #f0ad4e; }
#your-group-button:hover { background-color: #ec971f; }
.joined-group-button { background-color: #5bc0de; }
.joined-group-button:hover { background-color: #31b0d5; }
#joined-groups-container { display: flex; gap: 5px; }


#create-group-button {
    background-color: #7d4ba8;
    color: white;
}
#create-group-button:hover { background-color: #5e3881; }
.light-mode #create-group-button { color: white; }
.light-mode #create-group-button:hover { background-color: #5e3881; }

#settings-button {
    background: none;
    color: #fff;
    padding: 5px 10px;
}
.light-mode #settings-button { color: #333; }

#settings-button:hover { background-color: #555; }
.light-mode #settings-button:hover { background-color: #ccc; }

#settings-dropdown {
    display: none;
    position: absolute;
    top: 100%;
    right: 0;
    background-color: #505050;
    box-shadow: 0 8px 16px rgba(0,0,0,0.4);
    z-index: 10;
    padding: 10px;
    border-radius: 4px;
    min-width: 150px;
    transition: background-color 0.3s ease, box-shadow 0.3s ease;
}
.light-mode #settings-dropdown {
    background-color: #fff;
    box-shadow: 0 8px 16px rgba(0,0,0,0.1);
    border: 1px solid #ccc;
}
#settings-dropdown label {
    display: flex;
    align-items: center;
    color: #eee;
    font-size: 0.9em;
    margin-bottom: 5px;
}
.light-mode #settings-dropdown label { color: #333; }
#settings-dropdown label input[type="checkbox"] { margin-right: 5px; }
.filter-description {
    font-size: 0.7em;
    color: #bbb;
    margin-left: 5px;
}
.light-mode .filter-description { color: #666; }
#logout-button {
    display: block;
    margin-top: 10px;
    padding: 5px;
    background-color: #d9534f;
    color: white;
    text-align: center;
    text-decoration: none;
    border-radius: 3px;
    font-size: 0.9em;
}
#logout-button:hover { background-color: #c9302c; }


#group-info-bar {
    padding: 8px 15px;
    background-color: #383838;
    color: #ccc;
    font-size: 0.85em;
    border-bottom: 1px solid #404040;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}
.light-mode #group-info-bar {
    background-color: #e8e8e8;
    color: #444;
    border-bottom-color: #ccc;
}
#group-info-bar span { margin-right: 5px; }
#channel-list-display .channel-link {
    color: #a0cfff;
    text-decoration: underline;
    cursor: pointer;
    margin-right: 8px;
}
#channel-list-display .channel-link.active-channel {
    font-weight: bold;
    color: #fff;
    text-decoration: none;
}
.light-mode #channel-list-display .channel-link { color: #007bff; }
.light-mode #channel-list-display .channel-link.active-channel { color: #0056b3; }
#create-channel-button, #copy-group-url-button {
    padding: 3px 8px;
    font-size: 0.9em;
    background-color: #6a5acd;
    color: white;
    border: none;
    border-radius: 3px;
    cursor: pointer;
}
.light-mode #create-channel-button, .light-mode #copy-group-url-button { background-color: #8a7dcf; }

#messages {
    flex-grow: 1;
    padding: 15px;
    overflow-y: auto;
    border-bottom: 1px solid #404040;
    background-color: #606060;
    transition: background-color 0.3s ease;
}
.light-mode #messages {
    background-color: #f8f8f8;
    border-bottom-color: #ccc;
}
#typing-indicator {
    height: 20px;
    padding: 0 15px;
    font-size: 0.8em;
    color: #bbb;
    font-style: italic;
    background-color: #505050;
}
.light-mode #typing-indicator { background-color: #f0f0f0; color: #666;}


.message {
    margin-bottom: 25px;
    padding: 10px 15px;
    border-radius: 15px;
    max-width: 85%;
    word-wrap: break-word;
    position: relative;
    word-break: break-word;
    background-color: #777;
    color: #eee;
    align-self: flex-start;
    clear: both;
}
.my-message {
    background-color: #a0a0a0;
    align-self: flex-end;
}
.message.mentioned { background-color: #8a6d3b; }

.message .user {
    font-weight: bold;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    font-size: 0.9em;
    color: #ddd;
    cursor: pointer;
}
.light-mode .message .user { color: #555; }
.message .user::before {
    content: '';
    display: inline-block;
    width: 10px;
    height: 10px;
    background-color: #333;
    border-radius: 50%;
    margin-right: 6px;
}
.light-mode .message .user::before { background-color: #ccc; }
.message .user.online::before { background-color: #2ecc71; }

.reply-snippet {
    background-color: rgba(0,0,0,0.15);
    padding: 5px 8px;
    border-radius: 5px;
    margin-bottom: 5px;
    font-size: 0.85em;
    border-left: 3px solid #aaa;
    cursor: pointer;
}
.light-mode .reply-snippet { border-left-color: #888; background-color: rgba(0,0,0,0.05);}
.reply-snippet .user { font-size: 0.9em; font-weight: bold; }
.reply-snippet .reply-content { opacity: 0.8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}

.message .content {
    white-space: pre-wrap;
    font-size: 1em;
    color: #eee;
    margin-bottom: 8px;
}
.message .content .mention { background-color: #9b59b6; color: #fff; padding: 1px 4px; border-radius: 3px; font-weight: bold; }
.light-mode .message .content { color: #222; }

.filtered-message-applied .content {
    font-style: italic;
    color: #b3b3b3 !important;
}
.light-mode .filtered-message-applied .content { color: #666 !important; }

.link-preview {
    background-color: rgba(0,0,0,0.2);
    border-radius: 5px;
    margin-top: 5px;
    padding: 8px;
    border-left: 3px solid #7d4ba8;
    display: flex;
    gap: 10px;
}
.link-preview img { max-width: 80px; max-height: 80px; object-fit: cover; border-radius: 4px; }
.link-preview-text a { font-weight: bold; color: #a0cfff; text-decoration: none;}
.light-mode .link-preview-text a { color: #007bff; }
.link-preview-text p { font-size: 0.85em; margin: 3px 0 0 0; color: #ccc;}
.light-mode .link-preview-text p { color: #555;}


.message-image-container {
    max-width: 40%;
    margin-top: 5px;
    margin-bottom: 8px;
    border-radius: 5px;
    display: block;
    overflow: hidden;
    cursor: pointer;
}
.message .message-image {
    display: block;
    max-width: 100%;
    height: auto;
    border-radius: 5px;
}
.file-message-container {
    max-width: 60%;
    margin-top: 5px;
    margin-bottom: 8px;
    border-radius: 5px;
    background-color: rgba(0, 0, 0, 0.1);
    padding: 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
}
.light-mode .file-message-container { background-color: rgba(0, 0, 0, 0.05); }
.file-icon::before {
    content: '📄';
    font-size: 1.2em;
}
.file-details {
    display: flex;
    flex-direction: column;
}
.file-name {
    font-weight: bold;
    font-size: 0.9em;
    color: #eee;
}
.light-mode .file-name { color: #333; }
.file-size {
    font-size: 0.7em;
    color: #bbb;
}
.light-mode .file-size { color: #666; }
.poll-container { padding: 10px; border: 1px solid #888; border-radius: 8px; margin-top: 10px; }
.poll-question { font-weight: bold; margin-bottom: 10px; }
.poll-option { display: block; margin: 5px 0; }
.poll-option label { cursor: pointer; }
.poll-option .progress-bar { background: #555; height: 5px; border-radius: 3px; width: 0; transition: width 0.5s; }


.voice-message-container {
    margin-top: 5px;
    margin-bottom: 8px;
}
.voice-message-container audio {
    max-width: 250px;
    width: 100%;
    height: 40px;
}

.message-reactions {
    margin-top: 8px;
    display: flex;
    gap: 5px;
    flex-wrap: wrap;
    position: absolute;
    bottom: -22px;
    left: 10px;
}
.reaction {
    background-color: rgba(0,0,0,0.3);
    padding: 2px 6px;
    border-radius: 10px;
    font-size: 0.8em;
    cursor: pointer;
}
.light-mode .reaction {
    background-color: rgba(0,0,0,0.1);
}
.reaction.reacted-by-user {
    background-color: #7d4ba8;
    color: white;
}

.message-actions {
    position: absolute;
    top: 5px;
    right: 10px;
    display: flex;
    gap: 8px;
    z-index: 1;
    flex-wrap: wrap;
    justify-content: flex-end;
}
.message-actions button {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 0.75em;
    color: rgba(255, 255, 255, 0.6);
    padding: 0;
    text-decoration: underline;
    transition: color 0.2s ease;
    margin-left: 5px;
}
.light-mode .message-actions button { color: rgba(0, 0, 0, 0.5); }
.message-actions button:hover { color: #fff; }
.light-mode .message-actions button:hover { color: #000; }
.react-button { font-size: 1.2em; text-decoration: none; padding: 0 5px; }

.message-status {
    position: absolute;
    bottom: 3px;
    right: 10px;
    font-size: 0.7em;
    color: #ccc;
    display: flex;
    align-items: center;
}
.light-mode .message-status { color: #666; }
.edited-indicator {
    margin-right: 5px;
    font-style: italic;
}

.reaction-picker {
    position: absolute;
    background-color: #333;
    padding: 5px;
    border-radius: 15px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.5);
    display: flex;
    gap: 5px;
    z-index: 100;
}
.reaction-picker span {
    cursor: pointer;
    font-size: 1.5em;
    padding: 2px;
    transition: transform 0.2s;
}
.reaction-picker span:hover {
    transform: scale(1.2);
}

#input-area {
    display: flex;
    flex-direction: column;
    padding: 15px;
    background-color: #404040;
    gap: 10px;
    transition: background-color 0.3s ease;
    position: relative;
}
.light-mode #input-area { background-color: #e0e0e0; }

#mention-suggestions {
    display: none;
    position: absolute;
    bottom: calc(100% - 15px);
    left: 15px;
    right: 15px;
    max-height: 140px;
    overflow-y: auto;
    background-color: #383838;
    border: 1px solid #555;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    z-index: 100;
}
.light-mode #mention-suggestions { background-color: #f0f0f0; border-color: #ccc;}
.mention-suggestion-item {
    padding: 8px 12px;
    cursor: pointer;
    color: #eee;
    font-size: 0.9em;
}
.light-mode .mention-suggestion-item { color: #333; }
.mention-suggestion-item:hover { background-color: #5e3881; color: white; }
.mention-suggestion-item.selected { background-color: #7d4ba8; color: white; }
.mention-suggestion-item span { color: #bbb; margin-left: 5px; font-size: 0.9em; }


#message-input {
    width: 100%;
    padding: 10px;
    border: 1px solid #777;
    border-radius: 20px;
    font-size: 1em;
    outline: none;
    background-color: #e0e0e0;
    color: #333;
    box-sizing: border-box;
    transition: background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease;
}
.light-mode #message-input { background-color: #fff; border-color: #ccc; color: #333; }
#message-input::placeholder { color: #666; }
.light-mode #message-input::placeholder { color: #999; }

#input-area .button-row { display: flex; width: 100%; gap: 10px; }
#input-area .button-row button {
    flex-grow: 1;
    padding: 8px;
    border: none;
    border-radius: 20px;
    background-color: #7d4ba8;
    color: white;
    cursor: pointer;
    font-size: 0.9em;
    transition: background-color 0.3s ease;
}
#input-area .button-row button:hover, #input-area #send-button:hover { background-color: #5e3881; }

#input-area #send-button {
     padding: 10px 20px;
     font-size: 1em;
     width: 100%;
     border: none;
     border-radius: 20px;
     background-color: #7d4ba8;
     color: white;
     cursor: pointer;
}

#replying-to-indicator {
    font-size: 0.8em;
    color: #ccc;
    background-color: rgba(0,0,0,0.2);
    padding: 5px;
    border-radius: 5px;
    width: 100%;
    box-sizing: border-box;
}
#replying-to-indicator button { margin-left: 10px; color: #ff8a8a; cursor: pointer; background:none; border:none;}


.side-panel {
    position: fixed;
    top: 0;
    right: -300px;
    width: 280px;
    height: 100%;
    background-color: #333;
    box-shadow: -5px 0 15px rgba(0,0,0,0.5);
    z-index: 1001;
    transition: right 0.3s ease-in-out;
    padding: 15px;
    color: #eee;
}
.side-panel.open { right: 0; }
.light-mode .side-panel { background-color: #f4f4f4; color: #333; }
.close-panel-btn { position: absolute; top: 10px; right: 10px; background: none; border: none; font-size: 1.5em; color: #fff; cursor: pointer;}
.light-mode .close-panel-btn { color: #333;}
#online-users-list { list-style-type: none; padding: 0; }
#online-users-list li { display: flex; align-items: center; padding: 5px 0;}
#online-users-list .status-dot { width: 10px; height: 10px; background: #2ecc71; border-radius: 50%; margin-right: 10px;}
#online-users-list button { margin-left: auto; font-size: 0.8em; }

.dms-content { background-color: #444; margin: 5% auto; padding: 20px; border: 1px solid #888; width: 90%; max-width: 900px; height: 80vh; display: flex; flex-direction: column; border-radius: 10px;}
#dms-container { display: flex; flex: 1; min-height: 0; }
#dms-list-panel { width: 200px; border-right: 1px solid #666; overflow-y: auto;}
#dms-conversations-list { list-style-type: none; padding: 0; }
#dms-conversations-list li { padding: 10px; cursor: pointer; }
#dms-conversations-list li.active { background-color: #5e3881; }
#dms-chat-panel { flex: 1; display: flex; flex-direction: column;}
#dm-messages { flex: 1; overflow-y: auto; padding: 10px; }
#dm-input-area { display: flex; padding: 10px; border-top: 1px solid #666; gap: 5px;}
#dm-message-input { flex-grow: 1;}
.dms-close-btn { align-self: flex-end; }

.modal {
    display: none;
    position: fixed;
    z-index: 1000;
    padding-top: 60px;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    overflow: auto;
    background-color: rgba(0,0,0,0.9);
}
.modal-content {
    margin: auto;
    display: block;
    max-width: 90%;
    max-height: 80%;
    object-fit: contain;
}
.modal-content-form {
    background-color: #505050;
    margin: 15% auto;
    padding: 20px;
    border: 1px solid #888;
    width: 80%;
    max-width: 500px;
    border-radius: 8px;
}
#poll-form input { width: 100%; margin-bottom: 10px; box-sizing: border-box; }
#modal-caption {
    margin: auto;
    display: block;
    width: 80%;
    max-width: 700px;
    text-align: center;
    color: #ccc;
    padding: 10px 0;
    height: 150px;
}
.modal-close {
    position: absolute;
    top: 15px;
    right: 35px;
    color: #f1f1f1;
    font-size: 40px;
    font-weight: bold;
    transition: 0.3s;
    cursor: pointer;
}
.modal-close:hover, .modal-close:focus {
    color: #bbb;
    text-decoration: none;
    cursor: pointer;
}
#modal-download-button {
    display: block;
    margin: 20px auto;
    padding: 10px 20px;
    border: none;
    border-radius: 5px;
    background-color: #7d4ba8;
    color: white;
    cursor: pointer;
    font-size: 1em;
    transition: background-color 0.3s ease;
}
#modal-download-button:hover { background-color: #5e3881; }

#call-ui { background-color: rgba(0,0,0,1); display: none; padding: 0; justify-content: center; align-items: center; }
.call-container { position: relative; width: 100%; height: 100%; background: #111; }
#remote-video { width: 100%; height: 100%; object-fit: contain; }
#local-video { position: absolute; bottom: 20px; right: 20px; width: 150px; height: auto; border: 2px solid #fff; border-radius: 5px; }
.call-controls { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 15px; }
.call-controls button { padding: 10px 15px; font-size: 1em; border-radius: 50%; border: none; cursor: pointer;}
#end-call-btn { background-color: #e74c3c; }
#call-info { position: absolute; top: 20px; left: 50%; transform: translateX(-50%); color: #fff; background: rgba(0,0,0,0.5); padding: 5px 10px; border-radius: 5px;}

@media (max-width: 600px) {
    body { min-height: 100vh; }
    #chat-window {
        width: 100%;
        height: 100vh;
        border-radius: 0;
        border: none;
    }
    #header {
         font-size: 1em;
         padding: 8px 10px;
         flex-wrap: wrap;
    }
    #message-search-input { width: 100%; margin: 5px 0; order: 5; }
    #chat-title {
        width: auto;
        flex-grow: 1;
        text-align: left;
        margin-bottom: 0;
        order: -1;
    }
     .header-right-controls {
        order: 1;
        width: 100%;
        justify-content: space-around;
        margin-top: 5px;
    }
    #global-chat-button, #your-group-button, #create-group-button, .joined-group-button, .header-right-controls button {
        font-size: 0.8em;
        padding: 4px 8px;
        white-space: nowrap;
    }
    #settings-button { font-size: 0.8em; }
    #settings-dropdown { right: 0; left: auto; min-width: 120px; }
    #group-info-bar { font-size: 0.75em; padding: 6px 10px; gap: 5px; }
    #create-channel-button, #copy-group-url-button { font-size: 0.8em; }
    #messages { padding: 10px; }
    .message { max-width: 90%; }
    .message .user { font-size: 0.8em; margin-bottom: 3px; }
    .message .user::before { width: 14px; height: 14px; margin-right: 4px; }
    .message .content { font-size: 0.9em; }
    .message-image-container { max-width: 60%; }
    .file-message-container { max-width: 80%; }
    #input-area { padding: 10px; gap: 5px; flex-direction: column; }
    #message-input {
        margin: 0;
        border-radius: 15px;
        width: 100%;
    }
    #input-area .button-row { flex-wrap: wrap; }
    #input-area .button-row button {
        width: calc(50% - 5px);
    }
     #send-button { width: 100%; font-size: 1em; margin-top: 5px; }
     .message-actions { top: 2px; right: 8px; gap: 5px; }
     .message-status { bottom: 2px; right: 8px; }
     #local-video { width: 100px; }
}
"""

SCRIPTJS = r"""
const socket = io();

const msgsdiv = document.getElementById('messages');
const msginput = document.getElementById('message-input');
const sendbtn = document.getElementById('send-button');
const imginput = document.getElementById('image-file-input');
const fileinput = document.getElementById('generic-file-input');
const imgbtn = document.getElementById('attach-image-button');
const filebtn = document.getElementById('attach-file-button');
const recbtn = document.getElementById('record-voice-button');
const settingsbtn = document.getElementById('settings-button');
const settingsdrop = document.getElementById('settings-dropdown');
const filtertoggle = document.getElementById('message-filter-toggle');
const darktoggle = document.getElementById('dark-theme-toggle');
const lighttoggle = document.getElementById('light-theme-toggle');
const stagedfiles = document.getElementById('staged-files-indicator');
const pollbtn = document.getElementById('poll-button');
const typingdiv = document.getElementById('typing-indicator');

const creategroupbtn = document.getElementById('create-group-button');
const yourgroupbtn = document.getElementById('your-group-button');
const joinedgroups = document.getElementById('joined-groups-container');
const globalbtn = document.getElementById('global-chat-button');
const chattitle = document.getElementById('chat-title');

const groupbar = document.getElementById('group-info-bar');
const groupname = document.getElementById('group-name-display');
const membercount = document.getElementById('member-count-display');
const channellist = document.getElementById('channel-list-display');
const createchanbtn = document.getElementById('create-channel-button');
const copyurlbtn = document.getElementById('copy-group-url-button');
const notifytoggle = document.getElementById('notifications-toggle');
const searchinput = document.getElementById('message-search-input');
const mentionsdiv = document.getElementById('mention-suggestions');

const imgmodal = document.getElementById('image-modal');
const modalimg = document.getElementById('modal-image');
const modalclose = document.querySelector('.modal-close');
const modaldownload = document.getElementById('modal-download-button');
const reactpicker = document.getElementById('reaction-picker');

const onlinebtn = document.getElementById('online-users-button');
const onlinepanel = document.getElementById('online-users-panel');
const onlinelist = document.getElementById('online-users-list');

const replyingdiv = document.getElementById('replying-to-indicator');
let replyid = null;

const dmsbtn = document.getElementById('dms-button');
const dmspanel = document.getElementById('dms-panel');

const pollmodal = document.getElementById('poll-creation-modal');

const BANNEDWORDS = new Set([
    'anal', 'anus', 'arse', 'ass', 'asshole', 'bitch', 'blowjob', 'boner',
    'butt', 'clit', 'cock', 'cunt', 'dick', 'dildo', 'dyke', 'fag',
    'faggot', 'fellatio', 'fuck', 'fucker', 'fucking', 'genitals', 'handjob',
    'homo', 'jerkoff', 'jizz', 'kike', 'labia', 'muff', 'nigger', 'nigga',
    'orgasm', 'penis', 'piss', 'poop', 'porn', 'pussy', 'rape', 'rectum',
    'scrotum', 'sex', 'shit', 'slut', 'smegma', 'snatch', 'sperm', 'spunk',
    'squirt', 'tits', 'vagina', 'vulva', 'wank', 'whore'
]);

let thisuser = null;
let thisusername = null;
const MAXBYTES = 1 * 1024 * 1024;
const MAXVOICE = 60;
let messages = [];
let muted = JSON.parse(localStorage.getItem('muted') || '[]');

let stagedimg = null;
let stagedfile = null;
let stagedvoice = null;
let stagedpoll = null;

let editingid = null;
let editingtype = null;

let groupid = GROUPID;
let channelid = CHANNELID || 'general';
let groupdetails = { owner_sid: null, channels: [], members: [] };
let isowner = false;
let ownedid = null;
let online = [];

let recorder;
let chunks = [];
let recording = false;
let rectimer;

let typingtimer;
let lasttyping = 0;
let typers = {};

let mentionquery = null;
let mentionindex = -1;

let isfilter = localStorage.getItem('filter') === 'true';
filtertoggle.checked = isfilter;
let notifications = localStorage.getItem('notifications') === 'true';
if(notifications) Notification.requestPermission();
notifytoggle.checked = notifications;

let theme = localStorage.getItem('theme') || 'dark';

function settheme(name) {
    if (name === 'light') {
        document.body.classList.add('light-mode');
        lighttoggle.checked = true;
        darktoggle.checked = false;
    } else {
        document.body.classList.remove('light-mode');
        darktoggle.checked = true;
        lighttoggle.checked = false;
    }
    localStorage.setItem('theme', name);
}
settheme(theme);

function isbanned(text) {
    if (!text) return false;
    const words = text.toLowerCase().match(/\b\w+\b/g);
    if (!words) return false;
    return words.some(word => BANNEDWORDS.has(word));
}

function censor(text) {
    if (!text) return '';
    const pattern = new RegExp('\\b(' + Array.from(BANNEDWORDS).join('|') + ')\\b', 'gi');
    return text.replace(pattern, '***');
}

function formattime(timestamp) {
    const date = new Date(timestamp * 1000);
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
}
function markdown(text) {
    if (!text) return '';
    let escaped = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    escaped = escaped.replace(/@(\w+)/g, '<span class="mention">@$1</span>');
    escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    escaped = escaped.replace(/\*(.*?)\*/g, '<em>$1</em>');
    escaped = escaped.replace(/`(.*?)`/g, '<code>$1</code>');
    return escaped;
}

function readfile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = (e) => reject(e);
        reader.readAsDataURL(file);
    });
}

function updatecontrols() {
    if (groupid) {
        globalbtn.style.display = 'inline-block';
    } else {
        globalbtn.style.display = 'none';
    }
    if (ownedid) {
        creategroupbtn.style.display = 'none';
        yourgroupbtn.style.display = 'inline-block';
        yourgroupbtn.onclick = () => { window.location.href = '/group/' + ownedid; };
    } else {
        creategroupbtn.style.display = 'inline-block';
        yourgroupbtn.style.display = 'none';
    }
}

function updatechat() {
    if (groupid) {
        groupbar.style.display = 'flex';
        copyurlbtn.style.display = 'inline-block';
        groupname.textContent = `Group: ${groupid.split('/')[1]}`;
        chattitle.textContent = `Group: ${groupid.split('/')[1]} - #${channelid}`;
    } else {
        groupbar.style.display = 'none';
        copyurlbtn.style.display = 'none';
        chattitle.textContent = 'Global Chat';
    }
    updatecontrols();
}

function rendergroup() {
    if (!groupid || !groupdetails) return;
    membercount.textContent = groupdetails.members.length;
    channellist.innerHTML = '';
    (groupdetails.channels || []).forEach(channel => {
        const link = document.createElement('span');
        link.className = 'channel-link';
        link.textContent = `#${channel.name}`;
        link.dataset.channelId = channel.id;
        if (channel.id === channelid) {
            link.classList.add('active-channel');
        }
        link.onclick = () => switchchannel(channel.id);
        channellist.appendChild(link);
    });
    isowner = groupdetails.owner_name === thisusername;
    createchanbtn.style.display = isowner ? 'inline-block' : 'none';
    updatechat();
}

function switchchannel(newid) {
    if (newid === channelid) return;
    channelid = newid;
    socket.emit('switch_channel', { group_id: groupid, channel_id: newid });
    messages = [];
    msgsdiv.innerHTML = '';
    updatechat();
    rendergroup();
}

function updatereactions(el, msg) {
    let container = el.querySelector('.message-reactions');
    if (msg.reactions && Object.keys(msg.reactions).length > 0) {
        if (!container) {
            container = document.createElement('div');
            container.className = 'message-reactions';
            el.appendChild(container);
        }
        container.innerHTML = '';
        for (const [emoji, users] of Object.entries(msg.reactions)) {
            if (users.length > 0) {
                const span = document.createElement('span');
                span.className = 'reaction';
                span.textContent = `${emoji} ${users.length}`;
                if (users.includes(thisusername)) {
                    span.classList.add('reacted-by-user');
                }
                span.onclick = () => socket.emit('react', {
                    id: msg.id, emoji, group_id: msg.group_id, channel_id: msg.channel_id
                });
                container.appendChild(span);
            }
        }
    } else if (container) {
        container.remove();
    }
}
function renderpoll(msg, el) {
    if (!msg.poll) return;
    let container = el.querySelector('.poll-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'poll-container';
        const content = el.querySelector('.main-content');
        if (content) content.insertAdjacentElement('afterend', container);
        else el.querySelector('.user').insertAdjacentElement('afterend', container);
    }
    const question = `<div class="poll-question">${msg.poll.question}</div>`;
    const options = Object.entries(msg.poll.options).map(([option, votes]) => {
        const voted = votes.includes(thisusername);
        return `<div class="poll-option">
            <label>
                <input type="radio" name="poll-${msg.id}" value="${option}" ${voted ? 'checked' : ''} onclick="vote(${msg.id}, '${option}')">
                ${option} (${votes.length})
            </label>
        </div>`;
    }).join('');
    container.innerHTML = question + options;
}

function vote(id, option) {
    const msg = messages.find(m => m.id === id);
    socket.emit('vote', { id: id, option: option, group_id: msg.group_id, channel_id: msg.channel_id });
}

function updatemsg(msg) {
    const el = document.querySelector(`.message[data-id="${msg.id}"]`);
    if (!el) return;
    let content = el.querySelector('.main-content');
    if (msg.content) {
        if (!content) {
            content = document.createElement('div');
            content.classList.add('content', 'main-content');
            const att = el.querySelector('.message-image-container, .file-message-container, .voice-message-container, .poll-container');
            const status = el.querySelector('.message-status');
            if (att) el.insertBefore(content, att);
            else if (status) el.insertBefore(content, status);
            else el.appendChild(content);
        }
        let text = msg.content;
        if (isfilter && isbanned(msg.content)) {
             text = censor(msg.content);
             el.classList.add('filtered-message-applied');
        } else {
            el.classList.remove('filtered-message-applied');
        }
        content.innerHTML = markdown(text);
    } else if (content) {
        content.remove();
    }
    if (msg.poll) renderpoll(msg, el);
    if(msg.link_preview){
        let previewEl = el.querySelector('.link-preview');
        if(!previewEl) {
             previewEl = document.createElement('div');
             previewEl.className = 'link-preview';
             const contentEl = el.querySelector('.main-content');
             if(contentEl) contentEl.insertAdjacentElement('afterend', previewEl);
        }
        const p = msg.link_preview;
        let img = p.image ? `<img src="${p.image}" alt="Preview">` : '';
        previewEl.innerHTML = `${img}<div class="link-preview-text"><a href="${p.url}" target="_blank">${p.title||''}</a><p>${p.description||''}</p></div>`;
    }
    const span = el.querySelector('.message-status .timestamp');
    if (span) span.textContent = formattime(msg.timestamp);
    let edited = el.querySelector('.message-status .edited-indicator');
    if (msg.edited) {
        if (!edited) {
            edited = document.createElement('span');
            edited.className = 'edited-indicator';
            edited.textContent = 'Edited';
            el.querySelector('.message-status').prepend(edited);
        }
    } else if (edited) {
        edited.remove();
    }

    const insertionPoint = el.querySelector('.message-actions');
    let imgContainer = el.querySelector('.message-image-container');
    if (msg.image_url) {
        const filename = msg.image_filename || `image_${msg.id}.png`;
        if (imgContainer) {
            imgContainer.setAttribute('data-filename', filename);
            const img = imgContainer.querySelector('.message-image');
            img.src = msg.image_url;
            img.alt = filename;
            img.onclick = () => openimage(msg.image_url, filename);
        } else {
            imgContainer = document.createElement('div');
            imgContainer.className = 'message-image-container';
            imgContainer.setAttribute('data-filename', filename);
            const img = document.createElement('img');
            img.className = 'message-image';
            img.src = msg.image_url;
            img.alt = filename;
            img.addEventListener('click', () => openimage(msg.image_url, filename));
            imgContainer.appendChild(img);
            el.insertBefore(imgContainer, insertionPoint);
        }
    } else if (imgContainer) {
        imgContainer.remove();
    }

    let fileContainer = el.querySelector('.file-message-container');
    if (msg.file_url) {
        const filename = msg.file_filename || `file_${msg.id}`;
        if (fileContainer) {
            fileContainer.setAttribute('data-filename', filename);
            fileContainer.querySelector('.file-name').textContent = filename;
            fileContainer.onclick = () => download(msg.file_url, filename);
        } else {
            fileContainer = document.createElement('div');
            fileContainer.className = 'file-message-container';
            fileContainer.setAttribute('data-filename', filename);
            fileContainer.innerHTML = `<span class="file-icon"></span><div class="file-details"><span class="file-name">${filename}</span></div>`;
            fileContainer.addEventListener('click', () => download(msg.file_url, filename));
            el.insertBefore(fileContainer, insertionPoint);
        }
    } else if (fileContainer) {
        fileContainer.remove();
    }
    
    updatereactions(el, msg);
}


function showreacts(id, el) {
    reactpicker.innerHTML = '';
    EMOJIS.forEach(emoji => {
        const span = document.createElement('span');
        span.textContent = emoji;
        span.onclick = (e) => {
            e.stopPropagation();
            const msg = messages.find(m => m.id === id);
            socket.emit('react', { id: id, emoji: emoji, group_id: msg.group_id, channel_id: msg.channel_id });
            reactpicker.style.display = 'none';
        };
        reactpicker.appendChild(span);
    });
    const rect = el.getBoundingClientRect();
    reactpicker.style.top = `${rect.top - 45}px`;
    reactpicker.style.left = `${rect.left}px`;
    reactpicker.style.display = 'flex';
}
document.addEventListener('click', () => { if (reactpicker.style.display === 'flex') reactpicker.style.display = 'none'; });

function addmessage(msg, prepend = false) {
    if (muted.includes(msg.username)) return;
    const exists = document.querySelector(`.message[data-id="${msg.id}"]`);
    if (exists) { updatemsg(msg); return; }
    const nearbottom = msgsdiv.scrollHeight - msgsdiv.clientHeight <= msgsdiv.scrollTop + 150;
    const el = document.createElement('div');
    el.className = 'message';
    el.setAttribute('data-id', msg.id);
    if (msg.user === thisuser) el.classList.add('my-message');
    if (msg.mentions && msg.mentions.includes(thisusername)) el.classList.add('mentioned');
    
    const user = document.createElement('div');
    user.className = 'user';
    user.textContent = msg.user;
    el.appendChild(user);

    if (msg.reply_to_message) {
        const reply = msg.reply_to_message;
        const snippet = document.createElement('div');
        snippet.className = 'reply-snippet';
        snippet.innerHTML = `<div class="user">Replying to ${reply.user}</div><div class="reply-content">${reply.content_snippet}</div>`;
        snippet.onclick = () => { document.querySelector(`.message[data-id="${reply.id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); };
        el.appendChild(snippet);
    }
    if (msg.content) {
        const content = document.createElement('div');
        content.classList.add('content', 'main-content');
        let text = msg.content;
        if (isfilter && isbanned(msg.content)) { text = censor(msg.content); el.classList.add('filtered-message-applied'); }
        content.innerHTML = markdown(text);
        el.appendChild(content);
    }
    if (msg.link_preview) {
        const p = msg.link_preview;
        const pEl = document.createElement('div');
        pEl.className = 'link-preview';
        let img = p.image ? `<img src="${p.image}" alt="Preview">` : '';
        pEl.innerHTML = `${img}<div class="link-preview-text"><a href="${p.url}" target="_blank">${p.title||''}</a><p>${p.description||''}</p></div>`;
        el.appendChild(pEl);
    }
    if (msg.poll) renderpoll(msg, el);
    if (msg.voice_url) {
        const container = document.createElement('div');
        container.className = 'voice-message-container';
        const audio = new Audio(msg.voice_url);
        audio.controls = true;
        container.appendChild(audio);
        el.appendChild(container);
    }
    if (msg.image_url) {
        const container = document.createElement('div');
        container.className = 'message-image-container';
        const filename = msg.image_filename || `image_${msg.id}.png`;
        container.setAttribute('data-filename', filename);
        const img = document.createElement('img');
        img.className = 'message-image';
        img.src = msg.image_url;
        img.alt = filename;
        img.addEventListener('click', () => openimage(msg.image_url, filename));
        container.appendChild(img);
        el.appendChild(container);
    }
    if (msg.file_url) {
         const container = document.createElement('div');
         container.className = 'file-message-container';
         const filename = msg.file_filename || `file_${msg.id}`;
         container.setAttribute('data-filename', filename);
         const icon = document.createElement('span');
         icon.className = 'file-icon';
         container.appendChild(icon);
         const details = document.createElement('div');
         details.className = 'file-details';
         const namespan = document.createElement('span');
         namespan.className = 'file-name';
         namespan.textContent = filename;
         details.appendChild(namespan);
         container.appendChild(details);
         container.addEventListener('click', () => download(msg.file_url, filename));
         el.appendChild(container);
    }

    const actions = document.createElement('span');
    actions.className = 'message-actions';
    const react = document.createElement('button');
    react.textContent = '😊';
    react.className = 'react-button';
    react.onclick = (e) => { e.stopPropagation(); showreacts(msg.id, el); };
    actions.appendChild(react);
    const replybtn = document.createElement('button');
    replybtn.textContent = 'Reply';
    replybtn.onclick = () => setreply(msg.id);
    actions.appendChild(replybtn);

    if (msg.user === thisuser) {
       const del = document.createElement('button'); del.textContent = 'Delete'; del.onclick = () => deletemsg(msg.id); actions.appendChild(del);
       if (msg.content) { const edit = document.createElement('button'); edit.textContent = 'Edit Text'; edit.onclick = () => edittext(msg.id); actions.appendChild(edit); }
       if (msg.image_url) { const edit = document.createElement('button'); edit.textContent = 'Edit Image'; edit.onclick = () => editimage(msg.id); actions.appendChild(edit); }
       if (msg.file_url) { const edit = document.createElement('button'); edit.textContent = 'Edit File'; edit.onclick = () => editfile(msg.id); actions.appendChild(edit); }
    } else {
        const mute = document.createElement('button'); mute.textContent = muted.includes(msg.username) ? 'Unmute' : 'Mute'; mute.onclick = () => togglemute(msg.username); actions.appendChild(mute);
    }
    el.appendChild(actions);

    const status = document.createElement('span'); status.className = 'message-status';
    if (msg.edited) { const edited = document.createElement('span'); edited.className = 'edited-indicator'; edited.textContent = 'Edited'; status.appendChild(edited); }
    const time = document.createElement('span'); time.className = 'timestamp'; time.textContent = formattime(msg.timestamp); status.appendChild(time);
    el.appendChild(status);

    updatereactions(el, msg);
    if (prepend) msgsdiv.insertBefore(el, msgsdiv.firstChild);
    else { msgsdiv.appendChild(el); if (nearbottom) msgsdiv.scrollTop = msgsdiv.scrollHeight; }
}

function setreply(id) {
    replyid = id;
    const msg = messages.find(m => m.id === id);
    if (msg) {
        replyingdiv.innerHTML = `Replying to ${msg.user} <button onclick="cancelreply()">X</button>`;
        replyingdiv.style.display = 'block';
    }
}
function cancelreply() {
    replyid = null;
    replyingdiv.style.display = 'none';
}
function togglemute(name) {
    if (muted.includes(name)) muted = muted.filter(u => u !== name);
    else muted.push(name);
    localStorage.setItem('muted', JSON.stringify(muted));
    rerender();
}
function openimage(url, name = 'download') {
    modalimg.src = url;
    let filename = name;
     if (!filename.includes('.') && url.startsWith('data:image/')) {
         const match = url.match(/^data:image\/(png|jpeg|gif)/);
         if (match) { filename += '.' + (match[1]==='jpeg'?'jpg':match[1]); }
     }
    modaldownload.onclick = () => download(url, filename);
    imgmodal.style.display = 'block';
}
function closeimage() {
    imgmodal.style.display = 'none';
    modalimg.src = '';
    modaldownload.onclick = null;
}
modalclose.onclick = closeimage;
window.addEventListener('click', (e) => { if (e.target === imgmodal) closeimage(); });

function download(url, name = 'download') {
    const a = document.createElement('a'); a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

async function send() {
    const text = msginput.value.trim();
    if (!text && !stagedimg && !stagedfile && !stagedvoice && !stagedpoll) return;
    sendbtn.disabled = true; sendbtn.textContent = 'Sending...';
    let imgdata = null, filedata = null, voicedata = null;
    let imgname = stagedimg ? stagedimg.name : null;
    let filename = stagedfile ? stagedfile.name : null;
    let voicename = stagedvoice ? `voice-${Date.now()}.ogg` : null;
    const mentions = [...text.matchAll(/@(\w+)/g)].map(m => m[1]);

    try {
        const promises = [];
        if (stagedimg) promises.push(readfile(stagedimg).then(url => imgdata = url));
        if (stagedfile) promises.push(readfile(stagedfile).then(url => filedata = url));
        if (stagedvoice) promises.push(readfile(stagedvoice).then(url => voicedata = url));
        await Promise.all(promises);

        const payload = {
             text: text || null, image_url: imgdata, image_filename: imgname,
             file_url: filedata, file_filename: filename, voice_url: voicedata, voice_filename: voicename,
             poll: stagedpoll, replying_to: replyid, mentions: mentions
        };
        if (groupid) { payload.group_id = groupid; payload.channel_id = channelid; }
        socket.emit('message', payload);
        msginput.value = ''; stagedimg = null; stagedfile = null; stagedvoice = null; stagedpoll = null;
        imginput.value = null; fileinput.value = null;
        cancelreply(); updatebtn();
    } catch (error) {
        alert("Error reading file.");
    } finally {
         sendbtn.disabled = false; updatebtn(); msginput.focus();
    }
}
function deletemsg(id) {
    if (confirm('Delete this message?')) {
        const msg = messages.find(m => m.id === id);
        const payload = { id };
        if (msg && msg.group_id) { payload.group_id = msg.group_id; payload.channel_id = msg.channel_id; }
        socket.emit('delete', payload);
    }
}
function edittext(id) {
     const msg = messages.find(m => m.id === id);
     if (!msg || msg.user !== thisuser) return;
    const newtext = prompt('Edit:', msg.content || '');
    if (newtext !== null) {
        const trimmed = newtext.trim();
        if (trimmed === '' && !msg.image_url && !msg.file_url) return alert("Message cannot be empty.");
        if (trimmed !== (msg.content || '')) {
            const payload = { id: id, content: trimmed || null };
            if (groupid) { payload.group_id = groupid; payload.channel_id = channelid; }
            socket.emit('edittext', payload);
        }
    }
}
function editimage(id) {
    const msg = messages.find(m => m.id === id);
    if (!msg || msg.user !== thisuser || !msg.image_url) return;
    editingid = id; editingtype = 'image'; imginput.click();
}
function editfile(id) {
    const msg = messages.find(m => m.id === id);
    if (!msg || msg.user !== thisuser || !msg.file_url) return;
    editingid = id; editingtype = 'file'; fileinput.click();
}

function updatebtn() {
    let parts = [], indtext = "";
    if (msginput.value.trim() !== '') parts.push("Text");
    if (stagedimg) { parts.push("Image"); indtext += `Img: ${stagedimg.name} <button onclick="removestaged('image')">X</button> `; }
    if (stagedfile) { parts.push("File"); indtext += ` File: ${stagedfile.name} <button onclick="removestaged('file')">X</button>`; }
    if (stagedvoice) { parts.push("Voice"); indtext += ` Voice <button onclick="removestaged('voice')">X</button>`; }
    if (stagedpoll) { parts.push("Poll"); indtext += ` Poll: ${stagedpoll.question} <button onclick="removestaged('poll')">X</button>`; }
    
    sendbtn.textContent = parts.length > 0 ? `Send (${parts.join('+')})` : "Send";
    stagedfiles.innerHTML = indtext.trim().replace(/<button/g, '<button style="color:red; background:none; border:none; cursor:pointer;"');
    sendbtn.disabled = parts.length === 0;
}

function removestaged(type) {
    if (type === 'image') { stagedimg = null; imginput.value = null; }
    else if (type === 'file') { stagedfile = null; fileinput.value = null; }
    else if (type === 'voice') { stagedvoice = null; }
    else if (type === 'poll') { stagedpoll = null; }
    updatebtn();
}

async function record() {
    if (recording) {
        if(recorder) recorder.stop();
        clearTimeout(rectimer);
        recbtn.textContent = "Record Voice"; recbtn.style.backgroundColor = ''; recording = false;
    } else {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            recording = true; recbtn.textContent = "Stop (0s)"; recbtn.style.backgroundColor = 'red';
            chunks = []; recorder = new MediaRecorder(stream);
            recorder.ondataavailable = e => chunks.push(e.data);
            recorder.onstop = () => { stagedvoice = new Blob(chunks, { type: 'audio/ogg; codecs=opus' }); updatebtn(); stream.getTracks().forEach(t => t.stop()); };
            recorder.start();
            let s = 0;
            rectimer = setInterval(() => { s++; recbtn.textContent = `Stop (${s}s)`; if (s >= MAXVOICE) record(); }, 1000);
        } catch (err) { alert('Microphone access denied.'); recording = false; recbtn.textContent = "Record Voice"; recbtn.style.backgroundColor = ''; }
    }
}
function ontyping() {
    const now = new Date().getTime();
    if (now - lasttyping > 1500) socket.emit('typing', { group_id: groupid, channel_id: channelid });
    lasttyping = now; clearTimeout(typingtimer);
    typingtimer = setTimeout(() => { socket.emit('stoptyping', { group_id: groupid, channel_id: channelid }); }, 1500);
}

recbtn.addEventListener('click', record);
sendbtn.addEventListener('click', send);
msginput.addEventListener('keypress', (e) => { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); send(); }});
msginput.addEventListener('input', () => { updatebtn(); ontyping(); onmention(); });
msginput.addEventListener('keydown', onmentionkey);

imgbtn.addEventListener('click', () => { editingid = null; editingtype = null; imginput.click(); });
filebtn.addEventListener('click', () => { editingid = null; editingtype = null; fileinput.click(); });

function fileselect(e) {
    const file = e.target.files[0], type = e.target.id === 'image-file-input' ? 'image' : 'file';
    if (!file) { if(editingid){editingid = null; editingtype = null;} e.target.value = null; return; }
    if (file.size > MAXBYTES) { alert(`File too big.`); e.target.value = null; if (editingid) { editingid = null; editingtype = null; } return; }
    if (editingid !== null && editingtype !== null) {
         if ((editingtype !== type)) { alert('Wrong file type for edit.'); e.target.value = null; editingid = null; editingtype = null; return; }
         readfile(file)
             .then(url => {
                 const payload = { id: editingid, url: url, name: file.name };
                 if (groupid) { payload.group_id = groupid; payload.channel_id = channelid; }
                 socket.emit(editingtype === 'image' ? 'editimage' : 'editfile', payload);
             }).catch(err => alert("File error.")).finally(() => { editingid = null; editingtype = null; e.target.value = null; });
    } else {
        if (type === 'image') stagedimg = file; else stagedfile = file;
        updatebtn(); msginput.focus();
    }
}
imginput.addEventListener('change', fileselect);
fileinput.addEventListener('change', fileselect);

settingsbtn.addEventListener('click', (e) => { e.stopPropagation(); settingsdrop.style.display = settingsdrop.style.display==='block' ? 'none' : 'block'; });
window.addEventListener('click', (e) => {
    if (settingsdrop.style.display === 'block' && !settingsdrop.contains(e.target) && e.target !== settingsbtn) settingsdrop.style.display = 'none';
    if (mentionsdiv.style.display === 'block' && !mentionsdiv.contains(e.target) && e.target !== msginput) hidementions();
});

filtertoggle.addEventListener('change', (e) => { isfilter = e.target.checked; localStorage.setItem('filter', isfilter); rerender(); });
notifytoggle.addEventListener('change', e => { notifications = e.target.checked; localStorage.setItem('notifications', notifications); if(notifications) Notification.requestPermission(); });
function rerender() {
    const top = msgsdiv.scrollTop;
    msgsdiv.innerHTML = '';
    messages.forEach(msg => addmessage(msg));
    msgsdiv.scrollTop = top;
}

darktoggle.addEventListener('change', e => { if (e.target.checked) settheme('dark'); else if (!lighttoggle.checked) darktoggle.checked = true; });
lighttoggle.addEventListener('change', e => { if (e.target.checked) settheme('light'); else if (!darktoggle.checked) lighttoggle.checked = true; });
creategroupbtn.addEventListener('click', () => { socket.emit('creategroup'); });
globalbtn.addEventListener('click', () => { window.location.href = '/'; });
copyurlbtn.addEventListener('click', () => { navigator.clipboard.writeText(window.location.href).then(() => alert('URL copied!'), () => alert('Copy failed.')); });
createchanbtn.addEventListener('click', () => {
    if (!isowner || !groupid) return;
    const name = prompt("New channel name:");
    if (name && /^[a-zA-Z0-9]+$/.test(name)) socket.emit('createchannel', { group_id: groupid, name: name });
    else if (name) alert("Invalid name.");
});

function notify(title, body, interaction = false) {
    if (notifications && Notification.permission === 'granted' && document.hidden) new Notification(title, { body, requireInteraction: interaction });
}
searchinput.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    msgsdiv.querySelectorAll('.message').forEach(el => {
        const content = el.querySelector('.content')?.textContent.toLowerCase() || '';
        el.style.display = content.includes(term) ? '' : 'none';
    });
});

onlinebtn.addEventListener('click', () => onlinepanel.classList.toggle('open'));
document.querySelector('#online-users-panel .close-panel-btn').addEventListener('click', () => onlinepanel.classList.remove('open'));
dmsbtn.addEventListener('click', () => { dmspanel.style.display = 'block'; });
document.querySelector('.dms-close-btn').addEventListener('click', () => { dmspanel.style.display = 'none'; });

pollbtn.addEventListener('click', () => pollmodal.style.display = 'block');
document.querySelector('.poll-modal-close').addEventListener('click', () => pollmodal.style.display = 'none');
document.getElementById('add-poll-option-btn').addEventListener('click', () => {
    const opts = document.querySelectorAll('#poll-form .poll-option');
    if (opts.length < 4) {
        const newopt = document.createElement('input');
        newopt.type = 'text'; newopt.className = 'poll-option';
        newopt.placeholder = `Option ${opts.length + 1}`; newopt.required = true;
        document.getElementById('poll-additional-options').appendChild(newopt);
    } else { alert("Max 4 options."); }
});
document.getElementById('poll-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const q = document.getElementById('poll-question').value;
    const opts = Array.from(document.querySelectorAll('#poll-form .poll-option')).map(opt => opt.value.trim()).filter(Boolean);
    if (q && opts.length >= 2) {
        stagedpoll = { question: q, options: opts.reduce((a, v) => ({ ...a, [v]: [] }), {}) };
        pollmodal.style.display = 'none';
        updatebtn();
    } else alert("Poll needs a question and 2+ options.");
});

function onmention() {
    const text = msginput.value, pos = msginput.selectionStart;
    const match = text.slice(0, pos).match(/@(\w*)$/);
    if (match) {
        const query = match[1].toLowerCase(); mentionquery = match[0];
        const users = online.filter(u => u.username.toLowerCase().includes(query) || u.name.toLowerCase().includes(query)).slice(0, 5);
        if (users.length > 0) {
            mentionsdiv.innerHTML = users.map((u, i) => `<div class="mention-suggestion-item" data-index="${i}" data-username="${u.username}">${u.name} <span>@${u.username}</span></div>`).join('');
            mentionindex = -1; mentionsdiv.style.display = 'block';
            document.querySelectorAll('.mention-suggestion-item').forEach(item => item.addEventListener('click', (e) => selectmention(e.currentTarget.dataset.username)));
        } else hidementions();
    } else hidementions();
}
function hidementions() { mentionsdiv.style.display = 'none'; mentionquery = null; mentionindex = -1; }
function selectmention(name) {
    const text = msginput.value, pos = msginput.selectionStart;
    const before = text.slice(0, pos), after = text.slice(pos);
    const start = before.lastIndexOf(mentionquery);
    msginput.value = before.slice(0, start) + `@${name} ` + after;
    hidementions(); msginput.focus();
    const newpos = start + `@${name} `.length;
    msginput.setSelectionRange(newpos, newpos);
}
function onmentionkey(e) {
    if (mentionsdiv.style.display === 'none') return;
    const items = mentionsdiv.querySelectorAll('.mention-suggestion-item');
    if (!items.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); mentionindex = (mentionindex + 1) % items.length; updateselection(items); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); mentionindex = (mentionindex - 1 + items.length) % items.length; updateselection(items); }
    else if (e.key === 'Enter' || e.key === 'Tab') { if (mentionindex > -1) { e.preventDefault(); selectmention(items[mentionindex].dataset.username); } }
    else if (e.key === 'Escape') hidementions();
}
function updateselection(items) { items.forEach((it, i) => { it.classList.toggle('selected', i === mentionindex); }); }

socket.on('connect', () => {});

socket.on('info', (data) => {
    thisuser = data.name; thisusername = data.username; ownedid = data.owned_group_id;
    updatecontrols();
    joinedgroups.innerHTML = '';
    (data.joined_groups || []).forEach(id => {
        const btn = document.createElement('button'); btn.textContent = `Group ${id.split('/')[1].substring(0,4)}...`;
        btn.className = 'joined-group-button';
        btn.onclick = () => window.location.href = `/group/${id}`;
        joinedgroups.appendChild(btn);
    });
    if (groupid) socket.emit('joingroup', { group_id: groupid, channel_id: channelid });
    else socket.emit('getmessages');
    updatechat();
});
socket.on('userstatus', (data) => {
    online = data.online_users;
    onlinelist.innerHTML = '';
    online.forEach(user => {
        const li = document.createElement('li');
        li.innerHTML = `<span class="status-dot"></span>${user.name} <button onclick="startDM('${user.username}')">DM</button>`;
        onlinelist.appendChild(li);
    });
});
socket.on('globalmessages', (loaded) => {
    if (groupid) return;
    messages = loaded;
    rerender();
    msgsdiv.scrollTop = msgsdiv.scrollHeight;
});
socket.on('channelmessages', (data) => {
    if (data.group_id !== groupid || data.channel_id !== channelid) return;
    messages = data.messages;
    rerender();
    msgsdiv.scrollTop = msgsdiv.scrollHeight;
});
socket.on('newmessage', (msg) => {
    let display = (!msg.group_id && !groupid) || (msg.group_id === groupid && msg.channel_id === channelid);
    if (display) {
        if(!messages.find(m => m.id === msg.id && m.sid === msg.sid)) { messages.push(msg); addmessage(msg); }
        if (msg.user !== thisuser) {
            if (msg.mentions && msg.mentions.includes(thisusername)) notify(`Mention from ${msg.user}`, msg.content, true);
            else notify(`Message from ${msg.user}`, msg.content);
        }
    }
});
socket.on('typing', data => {
    let match = (!data.group_id && !groupid) || (data.group_id === groupid && data.channel_id === channelid);
    if (!match) return;
    if(data.typing) typers[data.user] = true; else delete typers[data.user];
    const names = Object.keys(typers);
    if(names.length > 0) {
        const str = names.slice(0, 3).join(', ');
        typingdiv.textContent = `${str}${names.length > 3 ? '...' : ''} is typing...`;
    } else typingdiv.textContent = '';
});
socket.on('deleted', (data) => {
    let match = (!data.group_id && !groupid) || (data.group_id === groupid && data.channel_id === channelid);
    if (match) { messages = messages.filter(msg => msg.id !== data.id); document.querySelector(`.message[data-id="${data.id}"]`)?.remove(); }
});
socket.on('updated', (updated) => {
    let match = (!updated.group_id && !groupid) || (updated.group_id === groupid && updated.channel_id === channelid);
    if (match) {
        const i = messages.findIndex(msg => msg.id === updated.id);
        if (i > -1) { messages[i] = updated; updatemsg(messages[i]); }
    }
});
socket.on('groupcreated', (data) => { window.location.href = '/group/' + data.group_id; });
socket.on('groupstate', (data) => {
    if (data.group_id !== groupid) return;
    groupdetails = data.details;
    rendergroup();
});
socket.on('channelcreated', (data) => { if (data.group_id === groupid) alert(`Channel "${data.name}" created!`); });
socket.on('error', (data) => { alert('Error: ' + data.message); sendbtn.disabled = false; updatebtn(); });
"""

def preview(url):
    try:
        if not re.match(r'http[s]?://', url):
            url = 'http://' + url
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
        response.raise_for_status()
        final_url = response.url
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.find('meta', property='og:title')
        description = soup.find('meta', property='og:description')
        image = soup.find('meta', property='og:image')
        title = title['content'] if title else (soup.title.string if soup.title else None)
        description = description['content'] if description else (soup.find('meta', attrs={'name': 'description'})['content'] if soup.find('meta', attrs={'name': 'description'}) else None)
        image_url = image['content'] if image and image.get('content') else None
        if image_url:
            image_url = urljoin(final_url, image_url)
        if title:
            return {'url': final_url, 'title': title, 'description': description, 'image': image_url}
    except Exception:
        return None
    return None

def isfiltered(text):
    if not text: return False
    return any(word in BANNEDWORDS for word in re.findall(r'\b\w+\b', text.lower()))

def ratelimit(ip):
    now = time.time()
    if ip not in ipreqs: ipreqs[ip] = deque()
    while ipreqs[ip] and ipreqs[ip][0] < now - REQWINDOW: ipreqs[ip].popleft()
    if len(ipreqs[ip]) >= REQLIMIT: return False
    ipreqs[ip].append(now); return True

def captcha():
    n1, n2 = random.randint(1, 10), random.randint(1, 10)
    op = random.choice(['+', '-'])
    if op == '-' and n1 < n2: n1, n2 = n2, n1
    return f"{n1} {op} {n2} = ?", n1 + n2 if op == '+' else n1 - n2

def auth(f):
    def decorated(*args, **kwargs):
        if 'username' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

def jsonifymsg(message):
    if not isinstance(message, dict): return message
    copy = message.copy()
    if 'reactions' in copy and isinstance(copy['reactions'], dict):
        safe = {e: list(u) if isinstance(u, set) else u for e, u in copy['reactions'].items()}
        copy['reactions'] = safe
    return copy

def jsonifymsgs(message_list):
    return [jsonifymsg(msg) for msg in message_list]

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        ans = request.form.get('captcha')
        if not all([user, pwd, ans]): error = 'All fields required.'
        elif int(ans) != session.get('captcha'): error = 'Incorrect math answer.'
        elif user not in creds or not check_password_hash(creds[user], pwd): error = 'Invalid credentials.'
        else: session['username'] = user; return redirect(url_for('index'))
    q, a = captcha()
    session['captcha'] = a
    return render_template_string(LOGINHTML, is_login=True, captcha_question=q, error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    global nextguest
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        ans = request.form.get('captcha')
        if not all([user, pwd, ans]): error = 'All fields required.'
        elif int(ans) != session.get('captcha'): error = 'Incorrect math answer.'
        elif user in creds: error = 'Username exists.'
        elif len(pwd) < 4: error = 'Password too short.'
        elif not re.match(r'^\w+$', user): error = 'Username must be alphanumeric.'
        else:
            creds[user] = generate_password_hash(pwd)
            userdata[user] = {'name': f'Guest-{nextguest}', 'sid': None, 'owned_group_id': None, 'joined_groups': set()}
            nextguest += 1
            session['username'] = user
            return redirect(url_for('index'))
    q, a = captcha()
    session['captcha'] = a
    return render_template_string(LOGINHTML, is_login=False, captcha_question=q, error=error)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
@auth
def index():
    if not ratelimit(request.remote_addr): return Response("Too many requests", 429)
    return render_template_string(INDEXHTML.format(cache_buster=int(time.time()), groupidjson='null', channelidjson='null', emojisjson=json.dumps(EMOJIS)))

@app.route('/group/<part1>/<part2>')
@auth
def group(part1, part2):
    if not ratelimit(request.remote_addr): return Response("Too many requests", 429)
    gid = f"{part1}/{part2}"
    if gid in groups:
        return render_template_string(INDEXHTML.format(cache_buster=int(time.time()), groupidjson=json.dumps(gid), channelidjson=json.dumps('general'), emojisjson=json.dumps(EMOJIS)))
    return redirect(url_for('index'))

@app.route('/style.css')
def style(): return Response(STYLECSS, mimetype='text/css')
@app.route('/script.js')
def script(): return Response(SCRIPTJS, mimetype='text/javascript')

def getstate(gid):
    g = groups.get(gid)
    if not g: return None
    chans = [{'id': cid, 'name': cdata['name']} for cid, cdata in g['channels'].items()]
    mems = [udata.get('name') for uname, udata in userdata.items() if udata.get('sid') in g['sids_in_group_room']]
    return {'owner_name': g['owner_name'], 'channels': chans, 'members': mems}

def getusers(gid=None):
    if gid and gid in groups: sids = groups[gid].get('sids_in_group_room', set()); relevant = {u:d for u,d in userdata.items() if d.get('sid') in sids}
    else: relevant = {u:d for u,d in userdata.items() if d.get('sid')}
    return [{'username': u, 'name': d['name']} for u, d in relevant.items()]

@socketio.on('connect')
def onconnect():
    if 'username' not in session: return False
    user, sid = session['username'], request.sid
    if user not in userdata: return False
    userdata[user]['sid'] = sid; sockets[user] = sid
    info = userdata[user]
    emit('info', {'name': info['name'], 'username': user, 'owned_group_id': info['owned_group_id'], 'joined_groups': list(info['joined_groups'])}, room=sid)
    socketio.sleep(0.1) 
    emit('userstatus', {'online_users': getusers()}, broadcast=True)

@socketio.on('disconnect')
def ondisconnect():
    sid = request.sid
    user = next((u for u, d in userdata.items() if d.get('sid') == sid), None)
    if user: userdata[user]['sid'] = None; sockets.pop(user, None)
    else: return
    info = clientstate.pop(sid, None)
    if info:
        gid = info['group_id']
        if gid in groups:
            groups[gid]['sids_in_group_room'].discard(sid)
            state = getstate(gid)
            if state: emit('groupstate', {'group_id': gid, 'details': state}, room=gid)
            emit('userstatus', {'online_users': getusers(gid)}, room=gid)
    socketio.sleep(0.1) 
    emit('userstatus', {'online_users': getusers()}, broadcast=True)

@socketio.on('getmessages')
def onreqmessages(): emit('globalmessages', jsonifymsgs(messages), room=request.sid)

def validatemedia(url, max_size):
    if not url or not isinstance(url, str) or not url.startswith('data:'): return None, 'Invalid format.'
    try: _, enc = url.split(',', 1); b = base64.b64decode(enc); return (b, None) if len(b) <= max_size else (None, 'Too big.')
    except: return None, 'Error processing.'

@socketio.on('creategroup')
def oncreategroup():
    if 'username' not in session: return
    user, sid = session['username'], request.sid
    if userdata[user]['owned_group_id']: return emit('error', {'message': 'You have a group.'}, room=sid)
    gid = f"{secrets.token_urlsafe(9)[:11]}/{''.join(random.choices(string.ascii_letters, k=15))}"
    groups[gid] = {'owner_name': user, 'channels': {'general': {'name': 'general', 'messages': [], 'next_message_id': 1}}, 'sids_in_group_room': set()}
    userdata[user]['owned_group_id'] = gid
    emit('groupcreated', {'group_id': gid}, room=sid)

@socketio.on('joingroup')
def onjoingroup(data):
    if 'username' not in session: return
    user, sid = session['username'], request.sid
    gid, cid = data.get('group_id'), data.get('channel_id', 'general')
    if not gid or gid not in groups: return emit('error', {'message': 'Group not found.'}, room=sid)
    g = groups[gid]
    if cid not in g['channels']: cid = 'general'
    join_room(gid, sid=sid); join_room(f"{gid}_{cid}", sid=sid)
    g['sids_in_group_room'].add(sid); clientstate[sid] = {'group_id': gid, 'channel_id': cid}
    if not userdata[user]['owned_group_id'] and g['owner_name'] != user: userdata[user]['joined_groups'].add(gid)
    state = getstate(gid)
    if state: emit('groupstate', {'group_id': gid, 'details': state}, room=gid)
    emit('channelmessages', {'group_id': gid, 'channel_id': cid, 'messages': jsonifymsgs(g['channels'][cid]['messages'])}, room=sid)
    emit('userstatus', {'online_users': getusers(gid)}, room=gid)

@socketio.on('switch_channel')
def onswitchchannel(data):
    sid, gid, new_cid = request.sid, data.get('group_id'), data.get('channel_id')
    if not gid or gid not in groups or not new_cid or new_cid not in groups[gid]['channels']: return emit('error', {'message':'Bad group/channel.'}, room=sid)
    info = clientstate.get(sid)
    if info and info['group_id'] == gid:
        old_cid = info['channel_id']
        if old_cid != new_cid:
            leave_room(f"{gid}_{old_cid}", sid=sid); join_room(f"{gid}_{new_cid}", sid=sid)
            clientstate[sid]['channel_id'] = new_cid
    emit('channelmessages', {'group_id': gid, 'channel_id': new_cid, 'messages': jsonifymsgs(groups[gid]['channels'][new_cid]['messages'])}, room=sid)

@socketio.on('createchannel')
def oncreatechannel(data):
    user, gid, name = session['username'], data.get('group_id'), data.get('name')
    if 'username' not in session or not gid or gid not in groups: return
    g = groups[gid]
    if g['owner_name'] != user or not name or not re.match(r"^[a-zA-Z0-9]+$", name) or name in g['channels']: return
    g['channels'][name] = {'name': name, 'messages': [], 'next_message_id': 1}
    state = getstate(gid)
    if state: emit('groupstate', {'group_id': gid, 'details': state}, room=gid)
    emit('channelcreated', {'group_id': gid, 'name': name}, room=gid)

def getsource(gid, cid):
    if gid and cid and gid in groups and cid in groups[gid]['channels']: return groups[gid]['channels'][cid]
    return None

def findmsg(mlist, mid):
    return next((m for m in mlist if m.get('id') == mid), None)

def findurl(text):
    if not text:
        return None
    url_pattern = re.compile(r'(?:https?://\S+)|(?:(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?)|(?:[a-zA-Z0-9-]+\.[a-zA-Z]{2,63})', re.IGNORECASE)
    match = url_pattern.search(text)
    return match.group(0) if match else None

def backgroundfetch(msg, room):
    url = findurl(msg.get('content'))
    if not url: return
    chan = getsource(msg.get('group_id'), msg.get('channel_id'))
    mlist = chan['messages'] if chan else messages
    p = preview(url)
    if p:
        original = findmsg(mlist, msg['id'])
        if original:
            original['link_preview'] = p
            if room:
                socketio.emit('updated', jsonifymsg(original), to=room)
            else:
                socketio.emit('updated', jsonifymsg(original), broadcast=True)

@socketio.on('message')
def onmessage(data):
    if 'username' not in session: return
    user = session['username']
    name, sid = userdata[user]['name'], request.sid
    if sid not in spamtimestamps: spamtimestamps[sid] = deque()
    now = time.time()
    spamtimestamps[sid].append(now)
    while spamtimestamps[sid] and spamtimestamps[sid][0] < now - SPAMWINDOW: spamtimestamps[sid].popleft()

    gid, cid = data.get('group_id'), data.get('channel_id')
    room = f"{gid}_{cid}" if gid else None

    if len(spamtimestamps[sid]) >= SPAMCOUNT:
        spam_message_content = f"{name} has been warned for spamming. Please slow down."
        botmsg = {'id':-1*int(time.time()*1000),'user':BOT,'content': spam_message_content, 'edited':False, 'timestamp':time.time(),'sid':'bot','reactions':{},'mentions':[]}
        if gid: botmsg.update({'group_id':gid,'channel_id':cid})
        if room: emit('newmessage', botmsg, to=room)
        else: emit('newmessage', botmsg, broadcast=True)
        spamtimestamps[sid].clear(); return

    text = data.get('text', '').strip() or None
    if not text and not any(data.get(k) for k in ['image_url','file_url','voice_url','poll']): return
    
    chan = getsource(gid, cid)
    if chan: mlist, mid, chan['next_message_id'] = chan['messages'], chan['next_message_id'], chan['next_message_id'] + 1
    else: global messages, nextid; mlist, mid, nextid = messages, nextid, nextid + 1
    
    msg = {'id':mid,'user':name,'username':user,'content':text,'image_url':None,'image_filename':None,'file_url':None,'file_filename':None,'voice_url':None,'voice_filename':None,'poll':None,'edited':False,'timestamp':time.time(),'sid':sid,'reactions':{},'reply_to_message':None,'mentions':data.get('mentions',[]),'link_preview':None}
    
    replyid = data.get('replying_to')
    if replyid:
        original = findmsg(mlist, replyid)
        if original:
            snip = (original['content'] or 'attachment')[:75]
            if len((original.get('content')or'')) > 75: snip+='...'
            msg['reply_to_message'] = {'id': original['id'], 'user': original['user'], 'content_snippet': snip}
    
    if data.get('poll'): msg['poll'] = data['poll']
    if data.get('image_url') and not validatemedia(data['image_url'],MAXBYTES)[1]: msg['image_url'],msg['image_filename']=data['image_url'],data.get('image_filename')
    if data.get('file_url') and not validatemedia(data['file_url'],MAXBYTES)[1]: msg['file_url'],msg['file_filename']=data['file_url'],data.get('file_filename')
    if data.get('voice_url') and not validatemedia(data['voice_url'],MAXBYTES)[1]: msg['voice_url'],msg['voice_filename']=data['voice_url'],data.get('voice_filename')

    if gid and cid: msg.update({'group_id':gid,'channel_id':cid})
    
    mlist.append(msg)
    if room: emit('newmessage', jsonifymsg(msg), to=room)
    else: emit('newmessage', jsonifymsg(msg), broadcast=True)
    
    if msg.get('content') and findurl(msg['content']): socketio.start_background_task(backgroundfetch, msg, room)
    if text and findurl(text):
        bot_reply_content = f"Replied to {name}: This user has sent an URL that might be dangerous. DO NOT ENTER THE WEBSITE!!"
        botmsg = {'id':-1*int(time.time()*1000+1),'user':BOT,'content':bot_reply_content,'edited':False,'timestamp':time.time(),'sid':'bot','reactions':{},'mentions':[]}
        if gid: botmsg.update({'group_id': gid, 'channel_id': cid})
        if room: emit('newmessage', botmsg, to=room)
        else: emit('newmessage', botmsg, broadcast=True)

@socketio.on('delete')
def ondelete(data):
    if 'username' not in session: return
    user, mid = session['username'], data.get('id')
    chan = getsource(data.get('group_id'), data.get('channel_id'))
    mlist = chan['messages'] if chan else messages
    todel = findmsg(mlist, mid)
    if todel and todel.get('username') == user:
        mlist.remove(todel)
        room = f"{data['group_id']}_{data['channel_id']}" if data.get('group_id') else None
        if room: emit('deleted', data, to=room)
        else: emit('deleted', data, broadcast=True)

@socketio.on('edittext')
def onedittext(data):
    if 'username' not in session: return
    user, mid, new = session['username'], data.get('id'), data.get('content','').strip() or None
    chan = getsource(data.get('group_id'), data.get('channel_id'))
    mlist = chan['messages'] if chan else messages
    toedit = findmsg(mlist, mid)
    if toedit and toedit.get('username') == user:
        if not new and not any(toedit.get(k) for k in ['image_url','file_url','voice_url']): return
        toedit['content'], toedit['edited'], toedit['timestamp'] = new, True, time.time()
        room = f"{data['group_id']}_{data['channel_id']}" if data.get('group_id') else None
        if room: emit('updated', jsonifymsg(toedit), to=room)
        else: emit('updated', jsonifymsg(toedit), broadcast=True)

def mediaedit(data, mtype):
    if 'username' not in session: return
    user, mid, url, name = session['username'], data.get('id'), data.get('url'), data.get('name')
    if not all([isinstance(mid, int), url, name]) or validatemedia(url, MAXBYTES)[1]: return
    chan = getsource(data.get('group_id'), data.get('channel_id'))
    mlist = chan['messages'] if chan else messages
    toedit = findmsg(mlist, mid)
    if toedit and toedit.get('username') == user:
        toedit[f'{mtype}_url'], toedit[f'{mtype}_filename'] = url, name
        toedit['edited'], toedit['timestamp'] = True, time.time()
        room = f"{data['group_id']}_{data['channel_id']}" if data.get('group_id') else None
        if room: emit('updated', jsonifymsg(toedit), to=room)
        else: emit('updated', jsonifymsg(toedit), broadcast=True)

@socketio.on('editimage')
def oneditimage(data): mediaedit(data, 'image')
@socketio.on('editfile')
def oneditfile(data): mediaedit(data, 'file')

@socketio.on('react')
def onreact(data):
    if 'username' not in session: return
    user, mid, emoji = session['username'], data.get('id'), data.get('emoji')
    if not emoji or not isinstance(emoji, str): return
    chan = getsource(data.get('group_id'), data.get('channel_id'))
    mlist = chan['messages'] if chan else messages
    msg = findmsg(mlist, mid)
    if msg:
        for old, users in list(msg['reactions'].items()):
            if user in users and old != emoji: users.remove(user);
            if not users: del msg['reactions'][old]
        if emoji not in msg['reactions']: msg['reactions'][emoji] = set()
        if user in msg['reactions'][emoji]: msg['reactions'][emoji].remove(user)
        else: msg['reactions'][emoji].add(user)
        if not msg['reactions'][emoji]: del msg['reactions'][emoji]
        payload = jsonifymsg(msg)
        room = f"{data['group_id']}_{data['channel_id']}" if data.get('group_id') else None
        if room: emit('updated', payload, to=room)
        else: emit('updated', payload, broadcast=True)

@socketio.on('vote')
def onvote(data):
    if 'username' not in session: return
    user, mid, opt = session['username'], data.get('id'), data.get('option')
    chan = getsource(data.get('group_id'), data.get('channel_id'))
    mlist = chan['messages'] if chan else messages
    msg = findmsg(mlist, mid)
    if msg and msg.get('poll') and opt in msg['poll']['options']:
        for o, v in msg['poll']['options'].items():
            if user in v: v.remove(user)
        msg['poll']['options'][opt].append(user)
        room = f"{data['group_id']}_{data['channel_id']}" if data.get('group_id') else None
        if room: emit('updated', jsonifymsg(msg), to=room)
        else: emit('updated', jsonifymsg(msg), broadcast=True)

@socketio.on('typing')
def ontyping(data):
    if 'username' not in session: return
    name = userdata[session['username']]['name']
    room = f"{data.get('group_id')}_{data.get('channel_id')}" if data.get('group_id') else None
    gid, cid = data.get('group_id'), data.get('channel_id')
    payload = {'user': name, 'typing': True, 'group_id': gid, 'channel_id': cid}
    emit('typing', payload, broadcast=True, include_self=False, room=room)

@socketio.on('stoptyping')
def onstoptyping(data):
    if 'username' not in session: return
    name = userdata[session['username']]['name']
    room = f"{data.get('group_id')}_{data.get('channel_id')}" if data.get('group_id') else None
    gid, cid = data.get('group_id'), data.get('channel_id')
    payload = {'user': name, 'typing': False, 'group_id': gid, 'channel_id': cid}
    emit('typing', payload, broadcast=True, include_self=False, room=room)

@socketio.on('signal')
def onsignal(data):
    if 'username' not in session: return
    sid = sockets.get(data['target_username'])
    if sid: emit('signal', { 'sender': session['username'], 'signal': data['signal'] }, room=sid)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)