import os
import urllib.request

os.makedirs("samples/real", exist_ok=True)

urls = {
    "samples/real/aia_g701_vancouver.pdf": "https://go.boarddocs.com/wa/vpswa/Board.nsf/files/C8GR686C60AB/$file/AIA%20G701%20Change%20Order.pdf",
    "samples/real/aia_g701_wheaton.pdf": "https://wheatonparkdistrict.com/wp-content/uploads/Chemical-Storage-Building-AGC-Change-order.pdf",
    "samples/real/civil_table_norman.pdf": "https://mccmeetingspublic.blob.core.usgovcloudapi.net/normanok-meet-3db7e75654d44477b07fc8d6565b04dc/ITEM-Attachment-001-cec54e51373b4385813599f047b88067.pdf",
    "samples/real/deductive_brookline.pdf": "https://resources.finalsite.net/images/v1765560417/a01uhvktjanlcdabhtkp/bhsproject_lambrianconstruction_changeorderno.pdf",
}

for path, url in urls.items():
    print(f"Downloading {path}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as f:
            f.write(resp.read())
        print(f"  -> Successfully saved {path}")
    except Exception as e:
        print(f"  -> Failed to download {path}: {e}")

print("\nDone downloading sample PDFs!")

