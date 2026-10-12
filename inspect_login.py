from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = context.new_page()
    page.goto('https://cms.bahria.edu.pk/Logins/Student/Login.aspx', wait_until='networkidle')
    page.wait_for_timeout(3000)
    print('=== PAGE TITLE ===')
    print(page.title())
    print('=== PAGE URL ===')
    print(page.url)
    print('=== PAGE HTML (first 5000 chars) ===')
    print(page.content()[:5000])
    print('=== FORM INPUTS ===')
    inputs = page.query_selector_all('input')
    for inp in inputs:
        attrs = {}
        for attr in ['id', 'name', 'type', 'placeholder']:
            val = inp.get_attribute(attr)
            if val:
                attrs[attr] = val
        if attrs:
            print(attrs)
    print('=== SELECT ELEMENTS ===')
    selects = page.query_selector_all('select')
    for sel in selects:
        attrs = {}
        for attr in ['id', 'name']:
            val = sel.get_attribute(attr)
            if val:
                attrs[attr] = val
        if attrs:
            print(attrs)
            options = sel.query_selector_all('option')
            for opt in options[:5]:
                val = opt.get_attribute("value")
                txt = opt.inner_text().strip()
                print(f'  option: {val} = {txt}')
    print('=== BUTTONS ===')
    buttons = page.query_selector_all('button, input[type=submit], input[type=button], a[href]')
    for btn in buttons[:20]:
        txt = btn.inner_text().strip() if btn.inner_text() else ''
        attrs = {}
        for attr in ['id', 'class', 'href', 'onclick']:
            val = btn.get_attribute(attr)
            if val:
                attrs[attr] = val
        if txt or attrs:
            print(f'  text: {txt[:50]} attrs: {attrs}')
    input('Press Enter to close...')
    browser.close()