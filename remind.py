import datetime
import json
import sys
import time
import tkinter as tk
from pathlib import Path

import cv2
import requests
from PIL import ImageGrab


BASE_PATH = Path(__file__).resolve().parent
CAPTURED_DIR = BASE_PATH / "captured"
SEARCH_DIR = BASE_PATH / "search"
CONFIG_FILE = BASE_PATH / "discord.json"
MATCH_THRESHOLD = 0.8
PRETEST_CAPTURE_FILE = CAPTURED_DIR / "captured_test.png"
PRETEST_TEMPLATE_FILE = SEARCH_DIR / "search_test.png"
MIDNIGHT_WAITING_EMOJI = "<:waiting:1487088573730787428>"


def ensure_directories() -> None:
	CAPTURED_DIR.mkdir(parents=True, exist_ok=True)
	SEARCH_DIR.mkdir(parents=True, exist_ok=True)


def load_discord_config(config_path: Path) -> tuple[str, str, str, str]:
	if not config_path.exists():
		print(f"[Error] Missing config file: {config_path}")
		print(f"Create discord.json in: {BASE_PATH}")
		sys.exit(1)

	try:
		with config_path.open("r", encoding="utf-8") as f:
			data = json.load(f)
	except json.JSONDecodeError as exc:
		print(f"[Error] Invalid JSON in {config_path}: {exc}")
		sys.exit(1)

	bot_token = str(data.get("bot_token", "")).strip()
	channel_id_time_shop = str(data.get("channel_id_time_shop", "")).strip()
	channel_id_drop_the_item = str(data.get("channel_id_drop_the_item", "")).strip()
	mention_text = str(data.get("mention_text", "")).strip()

	if not bot_token:
		print("[Error] discord.json must contain non-empty 'bot_token'.")
		sys.exit(1)
	if not channel_id_time_shop:
		print("[Error] discord.json must contain non-empty 'channel_id_time_shop'.")
		sys.exit(1)
	if not channel_id_drop_the_item:
		print("[Error] discord.json must contain non-empty 'channel_id_drop_the_item'.")
		sys.exit(1)

	return bot_token, channel_id_time_shop, channel_id_drop_the_item, mention_text


class RegionSelector:
	def __init__(self) -> None:
		self.coords: tuple[int, int, int, int] | None = None
		self.start_x = 0
		self.start_y = 0
		self.rect_id: int | None = None

		self.root = tk.Tk()
		self.root.title("Select Capture Region")
		self.root.attributes("-fullscreen", True)
		self.root.attributes("-topmost", True)
		self.root.attributes("-alpha", 0.30)
		self.root.configure(bg="black")

		self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0, cursor="cross")
		self.canvas.pack(fill="both", expand=True)

		self.canvas.bind("<ButtonPress-1>", self.on_press)
		self.canvas.bind("<B1-Motion>", self.on_drag)
		self.canvas.bind("<ButtonRelease-1>", self.on_release)
		self.root.bind("<Escape>", self.on_cancel)

		self.canvas.create_text(
			self.root.winfo_screenwidth() // 2,
			50,
			text="Drag to select the capture area. Press ESC to cancel.",
			fill="white",
			font=("Arial", 20, "bold"),
		)

	def run(self) -> tuple[int, int, int, int] | None:
		self.root.mainloop()
		return self.coords

	def on_press(self, event: tk.Event) -> None:
		self.start_x = int(event.x)
		self.start_y = int(event.y)
		if self.rect_id is not None:
			self.canvas.delete(self.rect_id)
		self.rect_id = self.canvas.create_rectangle(
			self.start_x,
			self.start_y,
			self.start_x,
			self.start_y,
			outline="red",
			width=3,
		)

	def on_drag(self, event: tk.Event) -> None:
		if self.rect_id is None:
			return
		self.canvas.coords(self.rect_id, self.start_x, self.start_y, int(event.x), int(event.y))

	def on_release(self, event: tk.Event) -> None:
		x0 = min(self.start_x, int(event.x))
		y0 = min(self.start_y, int(event.y))
		x1 = max(self.start_x, int(event.x))
		y1 = max(self.start_y, int(event.y))

		if x1 - x0 < 5 or y1 - y0 < 5:
			print("[Warning] Selected area is too small. Try again.")
			if self.rect_id is not None:
				self.canvas.delete(self.rect_id)
				self.rect_id = None
			return

		self.coords = (x0, y0, x1, y1)
		self.root.destroy()

	def on_cancel(self, _event: tk.Event) -> None:
		print("Selection canceled by user.")
		self.coords = None
		self.root.destroy()


def send_to_discord(bot_token: str, channel_id: str, image_path: Path, text_message: str = "") -> bool:
	url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
	headers = {"Authorization": f"Bot {bot_token}"}
	payload = {"content": text_message} if text_message else {}

	try:
		with image_path.open("rb") as f:
			files = {"file": (image_path.name, f, "image/png")}
			response = requests.post(url, headers=headers, data=payload, files=files, timeout=20)
	except requests.RequestException as exc:
		print(f"[Discord] Request error: {exc}")
		return False
	except OSError as exc:
		print(f"[Discord] File error: {exc}")
		return False

	if response.status_code == 200:
		print(f"[Discord] Upload success: {image_path}")
		return True

	print(f"[Discord] Upload failed ({response.status_code}): {response.text}")
	return False


def send_message_to_discord(bot_token: str, channel_id: str, text_message: str) -> bool:
	url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
	headers = {"Authorization": f"Bot {bot_token}"}
	payload = {"content": text_message}

	try:
		response = requests.post(url, headers=headers, json=payload, timeout=20)
	except requests.RequestException as exc:
		print(f"[Discord] Message request error: {exc}")
		return False

	if response.status_code == 200:
		print(f"[Discord] Message sent: {text_message}")
		return True

	print(f"[Discord] Message send failed ({response.status_code}): {response.text}")
	return False


def list_search_images(search_dir: Path) -> list[Path]:
	valid_ext = {".png", ".jpg", ".jpeg"}
	return [p for p in search_dir.iterdir() if p.is_file() and p.suffix.lower() in valid_ext]


def find_target_in_image(captured_path: Path, search_dir: Path, threshold: float = MATCH_THRESHOLD) -> bool:
	templates = list_search_images(search_dir)
	if not templates:
		print("[Detect] No templates found in search directory.")
		return False

	captured_img = cv2.imread(str(captured_path), cv2.IMREAD_GRAYSCALE)
	if captured_img is None:
		print(f"[Detect] Could not read captured image: {captured_path}")
		return False

	for template_path in templates:
		template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
		if template is None:
			print(f"[Detect] Skipping unreadable template: {template_path.name}")
			continue

		h, w = template.shape[:2]
		ch, cw = captured_img.shape[:2]
		if h > ch or w > cw:
			continue

		result = cv2.matchTemplate(captured_img, template, cv2.TM_CCOEFF_NORMED)
		_min_val, max_val, _min_loc, _max_loc = cv2.minMaxLoc(result)
		if max_val >= threshold:
			print(f"[Detect] Match found: {template_path.name} (score={max_val:.3f})")
			return True

	print("[Detect] No template matched.")
	return False


def run_initial_detection_test() -> bool:
	print("[PreTest] Running initial template detection test...")
	print(f"[PreTest] Capture source: {PRETEST_CAPTURE_FILE}")
	print(f"[PreTest] Template source: {PRETEST_TEMPLATE_FILE}")

	if not PRETEST_CAPTURE_FILE.exists():
		print(f"[PreTest] FAIL: missing file -> {PRETEST_CAPTURE_FILE}")
		return False

	if not PRETEST_TEMPLATE_FILE.exists():
		print(f"[PreTest] FAIL: missing file -> {PRETEST_TEMPLATE_FILE}")
		return False

	result = find_target_in_image(PRETEST_CAPTURE_FILE, SEARCH_DIR)
	if result:
		print("[PreTest] PASS: search_test.png was detected in captured_test.png")
	else:
		print("[PreTest] FAIL: search_test.png was not detected in captured_test.png")

	return result


def capture_and_process(
	bbox_coords: tuple[int, int, int, int],
	bot_token: str,
	channel_id: str,
	mention_text: str = "",
) -> None:
	timestamp = datetime.datetime.now().strftime("%y-%m-%d_%H-%M")
	save_path = CAPTURED_DIR / f"captured_{timestamp}.png"

	image = ImageGrab.grab(bbox=bbox_coords)
	image.save(save_path)
	print(f"[Capture] Saved: {save_path}")

	send_to_discord(bot_token, channel_id, save_path, "Selected screen region captured.")

	if find_target_in_image(save_path, SEARCH_DIR):
		alert_msg = "Detected target found in captured region."
		if mention_text:
			alert_msg = f"{mention_text} {alert_msg}"
		for attempt in range(10):
			send_to_discord(bot_token, channel_id, save_path, alert_msg)


def run_scheduler(capture_bbox: tuple[int, int, int, int], bot_token: str, channel_id: str, mention_text: str = "") -> None:
	print("Running immediate test capture...")
	capture_and_process(capture_bbox, bot_token, channel_id, mention_text)

	startup_msg = "Scheduler started!"
	if mention_text:
		startup_msg = f"{mention_text} {startup_msg}"
	send_message_to_discord(bot_token, channel_id, startup_msg)

	print("Scheduler started.")
	captured_recently = False
	captured_time = None
	prev_captured_hour = -1
	last_midnight_emoji_date: datetime.date | None = None

	while True:
		
		now = datetime.datetime.now()
		
		# Reset captured_recently after 2 hours to allow new captures
		if captured_recently and (abs(now.hour - captured_time.hour) >= 2 and prev_captured_hour != now.hour):
			captured_recently = False
			prev_captured_hour = now.hour

		if now.hour >= 0 and now.minute >= 0 and last_midnight_emoji_date != now.date():
			send_message_to_discord(bot_token, channel_id, MIDNIGHT_WAITING_EMOJI)
			last_midnight_emoji_date = now.date()

		if now.hour % 2 == 0 and now.minute >= 1:
			if not captured_recently:
				capture_and_process(capture_bbox, bot_token, channel_id, mention_text)
				captured_recently = True
				captured_time = datetime.datetime.now()

		time.sleep(300)  # Sleep for 5 minutes


def select_mode() -> int:
	print("=" * 40)
	print("모드를 선택하세요:")
	print("  1. 시간의 상점 모드 (짝수 정각마다 캡처)")
	print("  2. 드랍더템 모드 (30분 간격 캡처)")
	print("=" * 40)
	while True:
		raw = input("번호 입력 (1 또는 2): ").strip()
		if raw in ("1", "2"):
			return int(raw)
		print("[Error] 1 또는 2를 입력하세요.")


def run_drop_the_item_scheduler(
	capture_bbox: tuple[int, int, int, int],
	bot_token: str,
	channel_id: str,
	mention_text: str = "",
) -> None:
	while True:
		raw = input("남은 시간을 입력하세요 (분 단위, 정수): ").strip()
		if raw.isdigit():
			remaining_minutes = int(raw)
			break
		print("[Error] 양의 정수를 입력하세요.")

	initial_sleep = (remaining_minutes + 1) * 60
	print(f"[DropTheItem] {remaining_minutes + 1}분 대기 후 시작합니다...")
	time.sleep(initial_sleep)

	print("Running immediate capture before loop...")
	capture_and_process(capture_bbox, bot_token, channel_id, mention_text)

	startup_msg = "[드랍더템] 스케줄러 시작!"
	if mention_text:
		startup_msg = f"{mention_text} {startup_msg}"
	send_message_to_discord(bot_token, channel_id, startup_msg)

	print("[DropTheItem] 스케줄러 시작 (30분 간격).")
	elapsed_minutes = 0

	while True:
		time.sleep(60)
		elapsed_minutes += 1

		if elapsed_minutes >= 30:
			capture_and_process(capture_bbox, bot_token, channel_id, mention_text)
			elapsed_minutes = 0


def main() -> None:
	ensure_directories()
	run_initial_detection_test()
	bot_token, channel_id_time_shop, channel_id_drop_the_item, mention_text = load_discord_config(CONFIG_FILE)

	mode = select_mode()

	input("Press Enter to start the scheduler...")

	print("Opening region selector...")
	selector = RegionSelector()
	coords = selector.run()

	if coords is None:
		print("No region selected. Exiting.")
		return

	print(f"Selected coordinates: {coords}")
	try:
		if mode == 1:
			print("[Mode] 시간의 상점 모드")
			run_scheduler(coords, bot_token, channel_id_time_shop, mention_text)
		else:
			print("[Mode] 드랍더템 모드")
			run_drop_the_item_scheduler(coords, bot_token, channel_id_drop_the_item, mention_text)
	except KeyboardInterrupt:
		print("\nStopped by user.")


if __name__ == "__main__":
	main()
