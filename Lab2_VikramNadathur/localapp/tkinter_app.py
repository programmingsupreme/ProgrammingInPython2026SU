"""One-file Tkinter app for searching Artemis II images from NASA."""

from __future__ import annotations

import io
import json
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import quote

import requests

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None


NASA_IMAGES_SEARCH_URL = "https://images-api.nasa.gov/search"
OUTPUT_JSON = Path("artemis_ii_images.json")


class ArtemisImageApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Artemis II NASA Image Search")
        self.geometry("1050x700")
        self.minsize(850, 560)

        self.search_var = tk.StringVar(value="Artemis II")
        self.status_var = tk.StringVar(value="Ready")
        self.selected_image_url = ""
        self.selected_asset_url = ""
        self.items: list[dict] = []
        self.preview_photo = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top_bar = ttk.Frame(self, padding=12)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.columnconfigure(1, weight=1)

        ttk.Label(top_bar, text="Search").grid(row=0, column=0, padx=(0, 8))
        search_entry = ttk.Entry(top_bar, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        search_entry.bind("<Return>", lambda _event: self.fetch_images())

        ttk.Button(top_bar, text="Fetch Images", command=self.fetch_images).grid(row=0, column=2)

        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        left = ttk.Frame(main)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        main.add(left, weight=2)

        columns = ("title", "date", "center", "nasa_id")
        self.results_table = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        self.results_table.heading("title", text="Title")
        self.results_table.heading("date", text="Date")
        self.results_table.heading("center", text="Center")
        self.results_table.heading("nasa_id", text="NASA ID")
        self.results_table.column("title", width=320)
        self.results_table.column("date", width=100)
        self.results_table.column("center", width=80)
        self.results_table.column("nasa_id", width=180)
        self.results_table.grid(row=0, column=0, sticky="nsew")
        self.results_table.bind("<<TreeviewSelect>>", self.on_result_selected)

        scrollbar = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.results_table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_table.configure(yscrollcommand=scrollbar.set)

        right = ttk.Frame(main, padding=(12, 0, 0, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        main.add(right, weight=3)

        self.image_label = ttk.Label(right, text="Click Fetch Images, then select a result.", anchor="center")
        self.image_label.grid(row=0, column=0, sticky="nsew")

        self.details_text = tk.Text(right, height=10, wrap="word")
        self.details_text.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.details_text.configure(state="disabled")

        buttons = ttk.Frame(right)
        buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Open Image", command=self.open_image).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Open NASA Page", command=self.open_asset_page).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="Copy Image URL", command=self.copy_image_url).grid(row=0, column=2)

        status_bar = ttk.Frame(self, padding=(12, 0, 12, 10))
        status_bar.grid(row=2, column=0, sticky="ew")
        status_bar.columnconfigure(0, weight=1)
        ttk.Label(status_bar, textvariable=self.status_var).grid(row=0, column=0, sticky="w")

    def fetch_images(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Missing search", "Type a search term like Artemis II.")
            return

        self.status_var.set("Fetching images from NASA...")
        threading.Thread(target=self._fetch_images_worker, args=(query,), daemon=True).start()

    def _fetch_images_worker(self, query: str) -> None:
        try:
            images = fetch_artemis_images(query)
        except requests.RequestException as error:
            self.after(0, lambda: messagebox.showerror("NASA API Error", str(error)))
            self.after(0, lambda: self.status_var.set("Could not fetch NASA images."))
            return

        # FIX: OSError (e.g. permission denied) was uncaught and silently killed
        # the thread. Now caught and reported to the user.
        try:
            OUTPUT_JSON.write_text(json.dumps(images, indent=2), encoding="utf-8")
        except OSError as error:
            self.after(0, lambda: messagebox.showwarning("Save Warning", f"Could not save JSON: {error}"))

        items = images.get("collection", {}).get("items", [])
        self.after(0, lambda: self.load_results(items))

    def load_results(self, items: list[dict]) -> None:
        self.items = items

        # FIX: unpacking an empty sequence into *args raises TclError on some Tk
        # versions. An explicit loop is safe regardless of tree contents.
        for child in self.results_table.get_children():
            self.results_table.delete(child)

        self.selected_image_url = ""
        self.selected_asset_url = ""
        self.preview_photo = None
        self.image_label.configure(image="", text="Select an image result.")
        self.set_details("")

        for index, item in enumerate(items[:20]):
            data = image_data(item)
            self.results_table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    data.get("title", "Untitled"),
                    data.get("date_created", "")[:10],
                    data.get("center", ""),
                    data.get("nasa_id", ""),
                ),
            )

        # FIX: distinguish between "no results" and a successful load so the
        # "Saved …" suffix does not appear when nothing was found.
        count = min(len(items), 20)
        if count == 0:
            self.status_var.set("No results found.")
        else:
            self.status_var.set(f"Loaded {count} image result(s). Saved {OUTPUT_JSON}.")

    def on_result_selected(self, _event: tk.Event) -> None:
        selection = self.results_table.selection()
        if not selection:
            return

        item = self.items[int(selection[0])]
        data = image_data(item)
        image_url = preview_image_url(item)
        nasa_id = data.get("nasa_id", "")

        self.selected_image_url = image_url
        self.selected_asset_url = nasa_asset_page(nasa_id)

        self.set_details(
            "\n".join(
                [
                    f"Title: {data.get('title', 'Untitled')}",
                    f"NASA ID: {nasa_id}",
                    f"Date Created: {data.get('date_created', '')[:10]}",
                    f"NASA Center: {data.get('center', 'Unknown')}",
                    f"Keywords: {', '.join(data.get('keywords', []))}",
                    "",
                    data.get("description", ""),
                    "",
                    f"Image URL: {image_url}",
                ]
            )
        )

        if Image is None or ImageTk is None:
            self.image_label.configure(image="", text="Install Pillow to preview images.")
            self.status_var.set("Install Pillow with: python -m pip install Pillow")
            return

        # FIX: if no preview URL is available, spawning the worker would call
        # requests.get("") and raise a confusing MissingSchema error dialog.
        if not image_url:
            self.image_label.configure(image="", text="No preview image available for this result.")
            self.status_var.set("No preview URL found.")
            return

        self.status_var.set("Loading preview image...")
        threading.Thread(target=self._load_preview_worker, args=(image_url,), daemon=True).start()

    def _load_preview_worker(self, image_url: str) -> None:
        try:
            response = requests.get(image_url, timeout=20)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            image.thumbnail((620, 420))
            self.after(0, lambda: self.show_preview(image.copy()))
        except requests.RequestException as error:
            self.after(0, lambda: messagebox.showerror("Image Error", str(error)))
            self.after(0, lambda: self.status_var.set("Could not load preview image."))
        # FIX: Image.open / thumbnail can raise OSError or PIL.UnidentifiedImageError
        # (not a requests exception). Previously these would silently kill the thread
        # and leave the status bar stuck on "Loading preview image...".
        except Exception as error:  # noqa: BLE001
            self.after(0, lambda: messagebox.showerror("Image Error", f"Could not decode image: {error}"))
            self.after(0, lambda: self.status_var.set("Could not decode preview image."))

    def show_preview(self, image) -> None:
        self.preview_photo = ImageTk.PhotoImage(image)
        self.image_label.configure(image=self.preview_photo, text="")
        self.status_var.set("Ready")

    def set_details(self, text: str) -> None:
        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert("1.0", text)
        self.details_text.configure(state="disabled")

    def open_image(self) -> None:
        if self.selected_image_url:
            webbrowser.open(self.selected_image_url)

    def open_asset_page(self) -> None:
        if self.selected_asset_url:
            webbrowser.open(self.selected_asset_url)

    def copy_image_url(self) -> None:
        if self.selected_image_url:
            self.clipboard_clear()
            self.clipboard_append(self.selected_image_url)
            self.status_var.set("Image URL copied.")


def fetch_artemis_images(query: str) -> dict:
    params = {
        "q": query,
        "media_type": "image",
        "page": 1,
        "page_size": 20,
    }
    response = requests.get(NASA_IMAGES_SEARCH_URL, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def image_data(item: dict) -> dict:
    return (item.get("data") or [{}])[0]


def preview_image_url(item: dict) -> str:
    for link in item.get("links", []):
        if link.get("rel") == "preview" or link.get("render") == "image":
            return link.get("href", "")
    return ""


def nasa_asset_page(nasa_id: str) -> str:
    return f"https://images.nasa.gov/details/{quote(nasa_id, safe='')}"


if __name__ == "__main__":
    app = ArtemisImageApp()
    app.mainloop()
