# import cv2
# import pytesseract

# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# img = cv2.imread('maxresdefault.jpg')
# # Convert to grayscale for better OCR results
# gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
# text = pytesseract.image_to_string(gray, lang='eng')
# print(text)

import sqlite3

conn = sqlite3.connect("leads.db")
cur = conn.cursor()

cur.execute("DROP TABLE IF EXISTS theme_config")  # Deletes the table if it exists
conn.commit()
conn.close()