"""Generate only invented, public demonstration content. No private inputs."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlens.service import Service


def fixture(path, revised=False, insert=False):
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    width, height = A4
    def heading(kicker, title):
        c.setFillColor(HexColor("#224e3c")); c.rect(0,height-170,width,170,fill=1,stroke=0)
        c.setFillColor(HexColor("#b9dfaa"));c.setFont("Helvetica",10);c.drawString(44,height-51,kicker)
        c.setFillColor(HexColor("#ffffff"));c.setFont("Helvetica-Bold",26);c.drawString(44,height-98,title)
        c.setFillColor(HexColor("#32483c"))
    def line(text,y):
        c.setFont("Helvetica",12);c.drawString(44,y,text)
    heading("FIELD NOTES / PUBLIC DEMONSTRATION", "A small garden, measured.")
    line("The study follows six raised beds over eight weeks." if revised else "The study follows four raised beds over six weeks.",height-215)
    line("We record soil moisture before watering each morning.",height-245)
    line("The revised method includes a weekly calibration check." if revised else "The initial method uses a single calibration at setup.",height-275)
    line("These invented observations demonstrate a report comparison.",height-335)
    c.showPage()
    if insert:
        heading("NEW SECTION", "A note on rainfall.")
        line("Rainfall is recorded separately from irrigation.",height-215)
        c.showPage()
    heading("METHOD / FIGURE 1", "From reading to record.")
    c.setStrokeColor(HexColor("#527f5c"));c.setLineWidth(2)
    labels=["Read sensor", "Check calibration" if revised else "Average readings", "Save daily record"]
    for index,label in enumerate(labels):
        y=height-260-index*130
        c.setFillColor(HexColor("#edf3e8"));c.roundRect(140,y,315,70,10,fill=1,stroke=1)
        c.setFillColor(HexColor("#264b35"));c.setFont("Helvetica-Bold",14);c.drawCentredString(width/2,y+29,label)
        if index<2:
            c.line(width/2,y,width/2,y-55)
            c.line(width/2,y-55,width/2-6,y-47);c.line(width/2,y-55,width/2+6,y-47)
    line("Figure 1. Complete daily measurement workflow.",height-600)
    c.showPage()
    heading("OBSERVATIONS / TABLE 1", "A week at a glance.")
    line("Table 1. Invented measurements for demonstration only.",height-212)
    rows=[["Bed","Mean moisture","Observations"],["A","41%" if revised else "38%","7"],["B","43%","7"],["C","39%","7"]]
    if revised: rows.append(["D","42%","7"])
    for r,row in enumerate(rows):
        y=height-265-r*44
        c.setFillColor(HexColor("#e4eddd" if r==0 else "#f7f9f3"));c.rect(44,y-12,width-88,44,fill=1,stroke=0)
        c.setStrokeColor(HexColor("#ccd9c5"));c.line(44,y-12,width-44,y-12)
        c.setFillColor(HexColor("#294233"));c.setFont("Helvetica-Bold" if r==0 else "Helvetica",12)
        for x,text in zip([58,185,380],row):c.drawString(x,y+4,text)
    c.showPage();c.save()


if __name__ == "__main__":
    root=Path(__file__).parent / "public-demo"; root.mkdir(exist_ok=True)
    fixture(root/"before.pdf")
    fixture(root/"after.pdf",True)
    service=Service(root/".reportlens")
    service.compare_files(root/"before.pdf",root/"after.pdf",name="garden-review")
    import shutil
    for suffix in (".pdf", ".reportlens"):
        shutil.copyfile(service.root/("garden-review"+suffix),root/("garden-review"+suffix))
    print(root)
