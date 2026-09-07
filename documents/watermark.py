"""A diagonal cancellation mark that survives both Word and PDF rendering."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from docx.oxml import OxmlElement
from docx.shared import Cm


def add_cancellation_watermark(paragraph):
    canvas = Image.new('RGBA', (1200, 1200), (255, 255, 255, 0))
    try:
        font = ImageFont.truetype('DejaVuSans-Bold.ttf', 78)
    except OSError:
        font = ImageFont.load_default(size=78)
    ImageDraw.Draw(canvas).text((600, 600), 'FACTURE ANNULÉE', anchor='mm',
                               font=font, fill=(180, 35, 24, 70))
    canvas = canvas.rotate(35, resample=Image.Resampling.BICUBIC)
    stream = BytesIO()
    canvas.save(stream, format='PNG'); stream.seek(0)
    picture = paragraph.add_run().add_picture(stream, width=Cm(18))
    inline = picture._inline
    anchor = OxmlElement('wp:anchor')
    for key, value in {'distT':'0','distB':'0','distL':'0','distR':'0',
            'simplePos':'0','relativeHeight':'0','behindDoc':'1','locked':'0',
            'layoutInCell':'1','allowOverlap':'1'}.items():
        anchor.set(key, value)
    simple = OxmlElement('wp:simplePos'); simple.set('x','0'); simple.set('y','0');anchor.append(simple)
    for direction in ('H', 'V'):
        position=OxmlElement('wp:position'+direction);position.set('relativeFrom','page')
        align=OxmlElement('wp:align');align.text='center';position.append(align);anchor.append(position)
    anchor.append(inline.extent)
    anchor.append(OxmlElement('wp:wrapNone'))
    anchor.append(inline.docPr)
    anchor.append(inline.graphic)
    inline.getparent().replace(inline, anchor)
