from playwright.sync_api import sync_playwright
import os

os.environ['ENROLLMENT_NUMBER'] = '01-134252-139'
os.environ['PASSWORD'] = 'Abdullahuni123.'
os.environ['NTFY_SERVER'] = 'BahriaAssignments'
os.environ['INSTITUTION'] = '6'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = context.new_page()
    page.goto('https://cms.bahria.edu.pk/Logins/Student/Login.aspx', wait_until='networkidle')
    page.wait_for_timeout(2000)
    
    print("=== BEFORE LOGIN - Check all dropdowns ===")
    selects = page.query_selector_all('select')
    for sel in selects:
        sel_id = sel.get_attribute('id')
        print(f'Select: {sel_id}')
        for opt in sel.query_selector_all('option'):
            val = opt.get_attribute('value')
            txt = opt.inner_text().strip()
            print(f'  {val} = {txt}')
    
    page.fill("#BodyPH_tbEnrollment", '01-134252-139')
    page.fill("#BodyPH_tbPassword", 'Abdullahuni123.')
    page.select_option("#BodyPH_ddlInstituteID", "12")
    page.select_option("#BodyPH_ddlSubUserType", "None")
    page.click("#BodyPH_btnLogin")
    
    print("=== AFTER LOGIN CLICK ===")
    page.wait_for_timeout(5000)
    print(f'URL: {page.url}')
    print(f'Title: {page.title()}')
    
    print("=== ERROR MESSAGES ===")
    error_elements = page.query_selector_all('.alert, .error, .text-danger, [class*="error"], [class*="alert"], span[id*="Error"], span[id*="Message"]')
    for el in error_elements:
        txt = el.inner_text().strip()
        if txt:
            print(f'  {el.get_attribute("id") or el.get_attribute("class")}: {txt}')
    
    print("=== ALL VISIBLE TEXT ===")
    body_text = page.inner_text('body')
    print(body_text[:3000])
    
    input('Press Enter to close...')
    browser.close()