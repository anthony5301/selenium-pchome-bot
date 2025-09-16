"""
PChome 24h 自動搶購機器人

這個腳本會自動監控 PChome 24h 的追蹤清單 (Trace List)
當追蹤的商品變為可購買狀態時，會自動將其加入購物車並完成結帳流程。

主要流程：
1. 載入 Chrome 使用者設定檔以維持登入狀態。
2. 若未登入，會暫停並等待使用者手動登入。
3. 進入追蹤清單頁面，並以固定頻率刷新。
4. 偵測到「加入購物車」按鈕出現時，點擊按鈕。
5. 進入購物車，並執行結帳流程直到輸入 CVC 碼。
6. 根據 DRY_RUN 設定決定是否點擊最終的付款按鈕。
"""

import time

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import WebDriverException

from settings import CVC, DRY_RUN, CHROME_PROFILE

xpaths = {
    "add_to_cart_button": r"//button[contains(@class, 'add24hCart')]",
    "cart_checkout_button": r"//button[@data-regression='step1-checkout-btn']",
    "cvc_input": r"//input[@placeholder='CVC']",
    "confirm_payment_button": r"//button[@data-regression='step2-checkout-btn']",
}


def checkout():
    """
    執行從購物車到完成付款的結帳流程。

    1. 在購物車頁面點擊「前往結帳」。
    2. 在結帳頁面等待 CVC 輸入框出現並填入 CVC 碼。
    3. 根據 settings.py 中的 DRY_RUN 旗標，決定是否點擊最終的「確認付款」按鈕。
    """
    print("在購物車頁面點擊「結帳」...")
    WebDriverWait(driver, 10).until(
        expected_conditions.element_to_be_clickable(
            (By.XPATH, xpaths["cart_checkout_button"])
        )
    )
    checkout_button = driver.find_element(By.XPATH, xpaths["cart_checkout_button"])
    checkout_button.click()

    print("在結帳頁面輸入 CVC...")
    WebDriverWait(driver, 10).until(
        expected_conditions.element_to_be_clickable((By.XPATH, xpaths["cvc_input"]))
    )
    cvc_field = driver.find_element(By.XPATH, xpaths["cvc_input"])
    cvc_field.send_keys(CVC)

    if not DRY_RUN:
        print("點擊「確認付款」...")
        WebDriverWait(driver, 10).until(
            expected_conditions.element_to_be_clickable(
                (By.XPATH, xpaths["confirm_payment_button"])
            )
        )
        confirm_button = driver.find_element(By.XPATH, xpaths["confirm_payment_button"])
        driver.execute_script("arguments[0].click();", confirm_button)
    else:
        print("測試模式 (DRY_RUN=True)，未點擊最後的確認付款按鈕。")


options = webdriver.ChromeOptions()
options.add_argument(f"--user-data-dir={CHROME_PROFILE}")

driver = webdriver.Chrome(service=ChromeService(), options=options)
driver.set_page_load_timeout(120)

TRACE_LIST_URL = "https://ecvip.pchome.com.tw/web/MemberProduct/Trace"
CART_URL = "https://ecssl.pchome.com.tw/fsrwd/cart"
LOGIN_URL_IDENTIFIER = "login.htm"
CLICK_INTERVAL = 0.15

if __name__ == "__main__":
    print("正在前往追蹤清單，以檢查登入狀態...")
    driver.get(TRACE_LIST_URL)

    if LOGIN_URL_IDENTIFIER in driver.current_url:
        print("偵測到需要登入，請在瀏覽器中手動完成登入...")
        while LOGIN_URL_IDENTIFIER in driver.current_url:
            time.sleep(1)
        print("登入成功！")
    else:
        print("檢查完畢，已是登入狀態。")

    print("開始監控追蹤清單商品狀態...")
    while True:
        add_buttons = driver.find_elements(By.XPATH, xpaths["add_to_cart_button"])
        if add_buttons:
            print(f"找到了 {len(add_buttons)} 個可購買的商品！正在全部加入購物車...")
            for button in add_buttons:
                try:
                    button.click()
                    time.sleep(CLICK_INTERVAL)
                except WebDriverException as e:
                    print(f"點擊按鈕時發生 Selenium 相關錯誤: {e}")
            print("所有商品已加入購物車，準備結帳！")
            time.sleep(CLICK_INTERVAL)
            driver.get(CART_URL)
            checkout()
            time.sleep(100)
            break
        print("尚未有商品可購買，刷新頁面...")
        time.sleep(0.5)
        driver.refresh()
