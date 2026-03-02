import os
import requests
import time
from dotenv import load_dotenv

from datetime import datetime

load_dotenv()

MOLTBOOK_BASE = "https://www.moltbook.com/api/v1"
EXO_URL = "http://localhost:52415/v1/chat/completions"
API_KEY = os.getenv("MOLTBOOK_API_KEY")
MODEL = "mlx-community/Llama-3.2-3B-Instruct-8bit"

SYSTEM_PROMPT = """
You are an autonomous Moltbook agent.

Goals:
- Be intelligent
- Be concise
- Be helpful
- Be curious
- Build relationships

Never repeat yourself.
Never be generic.
"""

HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
}

def exo_chat(prompt, system_prompt=None):

    if system_prompt is None:
        system_prompt = SYSTEM_PROMPT

    r = requests.post(EXO_URL, json={
        "model": MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    })

    if r.status_code != 200:
        print("EXO ERROR:", r.text)
        return None

    data = r.json()

    if "choices" not in data:
        print("Malformed exo response:", data)
        return None

    return data["choices"][0]["message"]["content"]

def get_home():
    return requests.get(f"{MOLTBOOK_BASE}/home", headers=HEADERS).json()

def get_feed():
    return requests.get(
        f"{MOLTBOOK_BASE}/feed?sort=hot&limit=10",
        headers=HEADERS
    ).json()


def comment(post_id, content, parent_id=None):
    payload = {"content": content}

    if parent_id:
        payload["parent_id"] = parent_id

    r = requests.post(
        f"{MOLTBOOK_BASE}/posts/{post_id}/comments",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=payload
    )

    print("COMMENT RESPONSE:", r.status_code, r.text)
    return r.json()

def verify(verification_code, answer):
    return requests.post(
        f"{MOLTBOOK_BASE}/verify",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={
            "verification_code": verification_code,
            "answer": f"{float(answer):.2f}"
        }
    ).json()

def solve_challenge(text):

    MATH_SYSTEM_PROMPT = """
        You are a precise math solver.

        Solve the given problem.

        Return ONLY the final numeric answer with exactly 2 decimal places.

        Do not explain.
        Do not add text.
        Only output the number.
        """

    prompt = f"""
        Solve this verification challenge:

        {text}
    """

    response = exo_chat(prompt, system_prompt=MATH_SYSTEM_PROMPT)

    if not response:
        return None

    import re

    match = re.search(r'-?\d+(\.\d+)?', response)

    if match:
        return float(match.group())

    print("Solver failed:", response)
    return None

def handle_verification(response):

    if not response:
        print("No response")
        return

    verification = None
    verification_code = None

    # Case 1: comment verification
    if response.get("comment") and response["comment"].get("verification"):
        verification = response["comment"]["verification"]

    # Case 2: post verification
    elif response.get("post") and response["post"].get("verification"):
        verification = response["post"]["verification"]

    # Case 3: direct verification object
    elif response.get("verification"):
        verification = response["verification"]

    if not verification:
        print("No verification required")
        return

    verification_code = verification["verification_code"]
    challenge_text = verification["challenge_text"]

    print("\nVerification required")
    print("Challenge:", challenge_text)

    answer = solve_challenge(challenge_text)

    print("Answer:", answer)

    result = verify(verification_code, answer)

    print("Verification result:", result)

    return result


def comment_and_verify(post_id, content, parent_id=None):
    """
    Posts a comment (or reply), detects and completes Moltbook verification,
    and ensures the comment becomes publicly visible.
    """

    payload = {"content": content}

    if parent_id:
        payload["parent_id"] = parent_id

    try:
        r = requests.post(
            f"{MOLTBOOK_BASE}/posts/{post_id}/comments",
            headers={**HEADERS, "Content-Type": "application/json"},
            json=payload
        )

    except Exception as e:
        print("Network error posting comment:", e)
        return None

    print("\nCOMMENT RESPONSE:", r.status_code, r.text)

    if r.status_code == 429:
        retry = r.json().get("retry_after_seconds", 30)
        print(f"Rate limited. Sleeping {retry} seconds.")
        time.sleep(retry)
        return None

    if r.status_code != 201:
        print("Comment failed:", r.text)
        return None

    response = r.json()

    # Extract comment object
    comment = response.get("comment")

    if not comment:
        print("No comment object returned")
        return response

    # Check verification requirement
    verification = comment.get("verification")
    verification_status = comment.get("verification_status")

    if verification and verification_status == "pending":

        print("\nVerification required")
        print("Challenge:", verification["challenge_text"])

        answer = solve_challenge(verification["challenge_text"])

        if answer is None:
            print("Verification solve failed")
            return response

        formatted_answer = f"{answer:.2f}"

        if answer is None:
            print("Failed to solve challenge")
            return response

        formatted_answer = f"{answer:.2f}"

        print("Submitting verification answer:", formatted_answer)

        verify_response = requests.post(
            f"{MOLTBOOK_BASE}/verify",
            headers={**HEADERS, "Content-Type": "application/json"},
            json={
                "verification_code": verification["verification_code"],
                "answer": formatted_answer
            }
        )

        print("VERIFY RESPONSE:", verify_response.status_code, verify_response.text)

        if verify_response.status_code == 200:
            verify_json = verify_response.json()

            if verify_json.get("success"):
                print("Comment verified and published successfully")
                return verify_json
            else:
                print("Verification failed:", verify_json)
                return verify_json

        else:
            print("Verification request failed:", verify_response.text)
            return verify_response.json()

    elif verification_status == "verified":

        print("Comment already verified")
        return response

    else:

        print("Comment posted (trusted agent, no verification required)")
        return response

def get_post_content(post):
    return (
        post.get("content")
        or post.get("content_preview")
        or post.get("preview")
        or ""
    )

def clean_reply(reply):
    
    if not reply:
        return ""

    # Remove first char if == '"'
    if reply[0] == '"':
        reply = reply[1:]

    # remove last char if == '"'
    if reply[-1] == '"':
        reply = reply[:-1]

    return reply

replied_posts = set()
replied_comments = set()
engaged_posts = set()

while True:

    home = get_home()

    for activity in home.get("activity_on_your_posts", []):

        post_id = activity["post_id"]

        comments = requests.get(
            f"{MOLTBOOK_BASE}/posts/{post_id}/comments?sort=new",
            headers=HEADERS
        ).json()

        for c in comments:

            comment_id = c["id"]

            if comment_id in replied_comments:
                continue

            if c.get("author", {}).get("name") == home["your_account"]["name"]:
                continue

            reply = exo_chat(
                f"Reply helpfully and briefly to this Moltbook comment:\n\n{c['content']}"
            )

            # clean reply
            reply = clean_reply(reply)
            

            comment_and_verify(post_id, reply, parent_id=comment_id)

            replied_comments.add(comment_id)

            time.sleep(25)

    feed = get_feed()

    for post in feed.get("posts", []):

        if post["id"] in engaged_posts:
            continue

        content = get_post_content(post)
        print("POST OBJECT:", post)
        reply = exo_chat(
            f"Reply intelligently and briefly to this Moltbook post:\n\n"
            f"Title: {post.get('title', '')}\n"
            f"Content: {content}"
        )

        # clean reply
        reply = clean_reply(reply)

        comment_and_verify(post["id"], reply)

        engaged_posts.add(post["id"])

        time.sleep(25)

    time.sleep(1800)