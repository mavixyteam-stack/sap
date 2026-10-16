"""Default content for pages the client edits in the admin panel (founder story, legal pages, site settings)."""

SITE = {
    "site_url": "",            # blank = detect from the request / SITE_URL env
    "description": ("SAP Hardware makes architectural and furniture fittings: aluminium profiles, glass systems, "
                    "sliding and folding fittings, door hardware, kitchen and wardrobe solutions. Complete systems, "
                    "made in India, with display centres in Bengaluru, Chennai, Surat and Jodhpur."),
    "share_image": "",         # blank = generated automatically
    "ga4": "",
    "gsc_verification": "",
    "bing_verification": "",
}

FOUNDER = {
    "name": "Jitendra Agarwal",
    "role": "Founder, SAP Hardware",
    "photo": "assets/founder.webp",
    "headline": "From medicine to making things that last.",
    "intro": ("Jitendra Agarwal began his career in the medical field. What drew him away was a simple idea: "
              "good hardware quietly decides how well a home or an office works, and India deserved better."),
    "story": [
        "In 2013 he chose to build something of his own. SAP Hardware started small, with just seven products "
        "and a clear promise: honest quality, fair dealing, and parts that fit properly the first time.",
        "Step by step, the range grew with the people who used it. Architects asked for slimmer profiles. "
        "Fabricators asked for fittings that install faster. Homeowners asked for kitchens and wardrobes that "
        "glide, close softly and last. Every answer became a new product line.",
        "Today SAP Hardware offers more than 3,000 products across aluminium profiles, glass systems, sliding and "
        "folding fittings, door hardware, and kitchen and wardrobe solutions, supported by display centres in "
        "Bengaluru, Chennai, Surat and Jodhpur and more than 100 distributors across the country.",
        "Coming from medicine, he brought a habit of precision and care to the workshop floor: understand the "
        "real problem, be exact, and never compromise on quality where it matters.",
    ],
    "vision": ("To make well-engineered architectural and furniture hardware accessible to every home, office and "
               "craftsman in India, as complete systems rather than loose parts."),
    "values": [
        {"title": "Honest", "text": "Transparency with every client, in every deal."},
        {"title": "Standard", "text": "An easy buy-and-sell policy that protects your margins."},
        {"title": "Quality", "text": "Attention to detail in every product we choose."},
        {"title": "On time", "text": "Time is valuable, so we deliver when we say we will."},
    ],
    "milestones": [
        {"year": "2013", "label": "SAP Hardware begins with 7 products"},
        {"year": "2023", "label": "Display centres open for hands-on experience"},
        {"year": "Today", "label": "3,000+ products, 100+ distributors, 4 display centres"},
    ],
}

_CO = "Jagannath Hardware Pvt. Ltd. (trading as SAP Hardware)"
_ADDR = "6, 8th “A” Main Road, S.R. Nagar, Bengaluru – 560 027, India"
_MAIL = "saphardware2008@gmail.com"

LEGAL = {
    "privacy": {
        "title": "Privacy Policy",
        "updated": "16 October 2026",
        "body": f"""## Who we are
This website is operated by {_CO}, {_ADDR}. You can reach us at {_MAIL}. In this policy "we", "us" and "SAP Hardware" mean that company.

## What information we collect
- Enquiry details you choose to send us: name, phone number, email address, city, your message, and the product or series you asked about.
- Basic technical data such as your IP address and browser type, used to keep the site secure and to prevent spam.
- Cookie and similar data, described in our Cookie Policy.

We do not ask for payment details, and we do not sell products online.

## How we use it
- To reply to your enquiry and send the product information, drawings or support you asked for.
- To connect you with the nearest display centre or distributor.
- To keep the website secure, understand how it is used, and improve it.
- To meet legal obligations.

## Sharing
We do not sell your personal data. We share it only with the service providers who help us run the website (for example hosting and email delivery), with our distributors when you ask for a local contact, and where the law requires it.

## How long we keep it
We keep enquiry records for as long as needed to deal with your request and our business records, and then delete or anonymise them.

## Your choices and rights
You may ask us to access, correct or delete the personal data we hold about you, or withdraw your consent, at any time by writing to {_MAIL}. We will respond within a reasonable time and in line with applicable Indian law, including the Digital Personal Data Protection Act, 2023.

## Security
We use reasonable technical and organisational measures to protect your information. No method of transmission over the internet is completely secure, so we cannot guarantee absolute security.

## Children
This website is intended for businesses and adults. We do not knowingly collect personal data from children.

## Links to other sites
Our catalogues are shared through Google Drive links and other third-party sites. Their privacy practices are their own.

## Changes to this policy
We may update this policy from time to time. The date at the top shows when it was last changed.

## Contact
Questions about privacy? Email {_MAIL} or write to {_ADDR}.""",
    },
    "cookies": {
        "title": "Cookie Policy",
        "updated": "16 October 2026",
        "body": f"""## What are cookies
Cookies are small files placed on your device when you visit a website. Similar technologies, such as local storage, work in the same way. We use the word "cookies" for all of them.

## What we use
- Essential: we remember your cookie choice in your browser so we do not ask you again. This is stored on your device only.
- Analytics (only if you accept): if we enable Google Analytics, it sets cookies that tell us, anonymously, which pages are visited and how people find us. It loads only after you click "Accept".

We do not use advertising or tracking cookies, and we do not sell data collected through cookies.

## Staff tools
The administration area used by our team sets a secure sign-in cookie. Visitors never receive it.

## Managing cookies
You can change your choice by clearing this site's data in your browser settings, after which the cookie notice will appear again. You can also block or delete cookies in your browser settings; the website will continue to work, although some preferences may not be remembered.

## Changes
We may update this policy. The date at the top shows when it was last changed.

## Contact
Questions? Email {_MAIL}.""",
    },
    "terms": {
        "title": "Terms of Use",
        "updated": "16 October 2026",
        "body": f"""## About these terms
By using this website you agree to these terms. The site is operated by {_CO}, {_ADDR}.

## Information on this website
We take care to keep product names, codes, descriptions and images accurate, but they are provided for general information and may change without notice. Photographs and illustrations are indicative. Please confirm specifications, finishes and availability with our team before ordering.

## No online sales or prices
This website is a product catalogue and enquiry service. Prices are not shown and products cannot be bought online. Pricing is shared by our team or distributors on request.

## Enquiries
When you send an enquiry you confirm that the details you give are correct and that you agree to be contacted about it. How we handle your data is explained in our Privacy Policy.

## Intellectual property
The SAP name and logo, product designs, photographs, text and layout on this website belong to {_CO} or its licensors. You may not copy or reuse them for commercial purposes without written permission.

## Third-party links
Catalogue downloads are hosted on third-party services such as Google Drive. We are not responsible for their content or availability.

## Limitation of liability
To the fullest extent permitted by law, we are not liable for any loss arising from your use of this website or reliance on its content. Nothing here limits liability that cannot be excluded by law.

## Governing law
These terms are governed by the laws of India. Courts in Bengaluru, Karnataka have exclusive jurisdiction.

## Changes
We may update these terms from time to time. Continued use of the website means you accept the updated terms.

## Contact
Email {_MAIL}.""",
    },
}

EMAIL = {
    "to": ["saphardware2008@gmail.com"],
    "host": "", "port": 587, "user": "", "from_addr": "", "from_name": "SAP Hardware website", "password_enc": "",
}
