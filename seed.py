"""Load demo data: 5 players, sample challenges in every category, and some solves.

Usage:  python seed.py

Safe to run more than once: existing usernames and challenge titles are skipped.
For local demos only. Do not run it against a real event database.
"""
from datetime import timedelta

from app import create_app
from app.extensions import db
from app.models import CATEGORIES, DIFFICULTIES, Challenge, Solve, Submission, User, utcnow
from app.security import hash_flag, hash_password, new_salt, password_problems

PLAYERS = [
    # username, display name, password
    ("neo", "Neo Anderson", "Matrix-Red-Pill-2026"),
    ("trinity", "Trinity", "Rabbit-Hole-Follow-77"),
    ("morpheus", "Morpheus", "Free-Your-Mind-1999"),
    ("cipher", "Cipher", "Steak-Is-Real-404"),
    ("oracle", "The Oracle", "Cookies-And-Tea-31"),
]

CHALLENGES = [
    # title, category, difficulty, points, flag, description
    ("Hidden in Plain Sight", "Web", "Easy", 100, "flag{view_source_is_your_friend}",
     "The developer left a note for themselves somewhere on the login page.\n\nLook closer than the browser wants you to."),
    ("Cookie Monster", "Web", "Medium", 250, "flag{n3v3r_trust_th3_cl13nt}",
     "The admin panel checks a cookie to decide who you are.\nCan you convince it you are someone else?"),
    ("Template Trouble", "Web", "Hard", 400, "flag{ssti_{{7*7}}_equals_49}",
     "A greeting card generator renders whatever name you give it.\n\nMaybe a little too faithfully."),
    ("Caesar's Salad", "Crypto", "Easy", 100, "flag{rotate_and_repeat}",
     "synt{ebgngr_naq_ercrng}\n\nAn emperor would know what to do."),
    ("XOR Marks the Spot", "Crypto", "Medium", 300, "flag{single_byte_keys_are_weak}",
     "A message was XORed with one repeating byte and hex-encoded.\nBrute force is closer than you think."),
    ("Broken RSA", "Crypto", "Insane", 600, "flag{small_e_big_problems}",
     "n is huge, e is 3, and the message was short.\n\nWhat could possibly go wrong?"),
    ("Metadata Never Lies", "Forensics", "Easy", 150, "flag{exif_tells_all}",
     "A photo was posted from a secret location.\nThe camera remembers more than the photographer intended."),
    ("Packet Whisperer", "Forensics", "Hard", 450, "flag{dns_exfil_detected}",
     "Someone smuggled data out of the network one tiny query at a time.\n\nReassemble what they stole."),
    ("Permission Denied?", "Linux", "Medium", 250, "flag{suid_bits_are_dangerous}",
     "You have a low-privilege shell. The flag is readable only by root.\nFind the binary that trusts you too much."),
    ("Port Knocking", "Networking", "Medium", 300, "flag{knock_knock_whos_there}",
     "The server only opens its door if you knock in the right order.\n\nThe sequence is hidden in the banner of another service."),
    ("Sanity Check", "Misc", "Easy", 50, "flag{welcome_to_the_arena}",
     "Welcome! Submit flag{welcome_to_the_arena} to make sure everything works."),
    ("Esoteric Echoes", "Misc", "Insane", 500, "flag{brainf_is_turing_complete}",
     "++++++++[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]\n\nThe rest of the program is left as an exercise."),
]

# Which challenge titles each player has solved, and roughly how long ago (hours).
SOLVES = {
    "neo": [("Sanity Check", 70), ("Hidden in Plain Sight", 66), ("Caesar's Salad", 60),
            ("Cookie Monster", 40), ("XOR Marks the Spot", 30), ("Permission Denied?", 12),
            ("Broken RSA", 3)],
    "trinity": [("Sanity Check", 71), ("Hidden in Plain Sight", 65), ("Metadata Never Lies", 50),
                ("Port Knocking", 35), ("Packet Whisperer", 20), ("Template Trouble", 6)],
    "morpheus": [("Sanity Check", 69), ("Caesar's Salad", 58), ("XOR Marks the Spot", 44),
                 ("Permission Denied?", 25)],
    "cipher": [("Sanity Check", 68), ("Hidden in Plain Sight", 52), ("Metadata Never Lies", 15)],
    "oracle": [("Sanity Check", 64), ("Esoteric Echoes", 9)],
}

WRONG_GUESSES = [
    ("cipher", "Cookie Monster", "flag{admin=true}"),
    ("cipher", "Broken RSA", "flag{rsa}"),
    ("morpheus", "Template Trouble", "flag{{7*7}}"),
    ("oracle", "Caesar's Salad", "flag{caesar}"),
    ("trinity", "Broken RSA", "flag{e_is_three}"),
]


def main() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()
        min_len = app.config["MIN_PASSWORD_LENGTH"]
        now = utcnow()

        users = {}
        for username, name, password in PLAYERS:
            user = User.query.filter_by(username=username).first()
            if user is None:
                problems = password_problems(password, min_len, username)
                if problems:
                    raise SystemExit(f"Seed password for {username} is invalid: {problems}")
                user = User(username=username, display_name=name, role="user",
                            password_hash=hash_password(password), must_change_password=False,
                            created_at=now - timedelta(days=4))
                db.session.add(user)
                print(f"  + player {username}")
            users[username] = user

        challenges = {}
        for title, category, difficulty, points, flag, description in CHALLENGES:
            assert category in CATEGORIES and difficulty in DIFFICULTIES
            ch = Challenge.query.filter_by(title=title).first()
            if ch is None:
                salt = new_salt()
                ch = Challenge(title=title, category=category, difficulty=difficulty, points=points,
                               description=description, flag_salt=salt, flag_hash=hash_flag(flag, salt),
                               created_at=now - timedelta(days=5))
                db.session.add(ch)
                print(f"  + challenge {title}")
            challenges[title] = ch
        db.session.flush()

        flags = {c[0]: c[4] for c in CHALLENGES}
        for username, solved in SOLVES.items():
            user = users[username]
            for title, hours_ago in solved:
                ch = challenges[title]
                if Solve.query.filter_by(user_id=user.id, challenge_id=ch.id).first():
                    continue
                when = now - timedelta(hours=hours_ago)
                db.session.add(Solve(user_id=user.id, challenge_id=ch.id,
                                     points_awarded=ch.points, solved_at=when))
                db.session.add(Submission(user_id=user.id, challenge_id=ch.id, submitted=flags[title],
                                          is_correct=True, ip="127.0.0.1", created_at=when))

        for username, title, guess in WRONG_GUESSES:
            user, ch = users[username], challenges[title]
            exists = Submission.query.filter_by(user_id=user.id, challenge_id=ch.id, submitted=guess).first()
            if not exists:
                db.session.add(Submission(user_id=user.id, challenge_id=ch.id, submitted=guess,
                                          is_correct=False, ip="127.0.0.1",
                                          created_at=now - timedelta(hours=8)))

        db.session.commit()

        print("\nDemo players (password login):")
        for username, _, password in PLAYERS:
            print(f"  {username:<10} {password}")
        print("\nChallenge flags:")
        for title, _, _, points, flag, _ in CHALLENGES:
            print(f"  {title:<24} {points:>4} pts  {flag}")
        print("\nSeed complete.")


if __name__ == "__main__":
    main()
