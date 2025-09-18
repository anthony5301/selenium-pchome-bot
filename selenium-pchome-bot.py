"""
PChome 24h 自動搶購機器人

這個腳本會自動監控 PChome 24h 追蹤清單中的商品狀態
當追蹤的商品變為可購買狀態時，會自動將其加入購物車並完成結帳流程。

主要功能：
1. 載入 Chrome 使用者設定檔以維持登入狀態。
2. 若未登入，會暫停並等待使用者手動登入。
3. 輪詢追蹤清單中的商品，直到所有商品都顯示為「ForSale」。
4. 將所有可購買商品加入購物車。
5. 進入購物車，並執行結帳流程直到輸入 CVC 碼。
6. 根據 DRY_RUN 設定決定是否點擊最終的付款按鈕。
"""

import time
import json
import logging
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from settings import CVC, DRY_RUN, CHROME_PROFILE

xpaths = {
    "cart_checkout_button": r"//button[@data-regression='step1-checkout-btn']",
    "cvc_input": r"//input[@placeholder='CVC']",
    "confirm_payment_button": r"//button[@data-regression='step2-checkout-btn']",
}

TRACE_LIST_URL = "https://ecvip.pchome.com.tw/web/MemberProduct/Trace"
CART_URL = "https://ecssl.pchome.com.tw/fsrwd/cart"
LOGIN_URL_IDENTIFIER = "login.htm"
INTERVAL = 0.10


def checkout(maindriver):
    """
    執行從購物車到完成付款的結帳流程。

    流程：
    1. 在購物車頁面點擊「結帳」。
    2. 在結帳頁面等待 CVC 輸入框出現並填入 CVC 碼。
    3. 根據 settings.py 中的 DRY_RUN 旗標，決定是否點擊最終的「確認付款」按鈕。
    """
    logging.info("在購物車頁面點擊「結帳」...")
    WebDriverWait(maindriver, 10).until(
        EC.element_to_be_clickable((By.XPATH, xpaths["cart_checkout_button"]))
    )
    maindriver.find_element(By.XPATH, xpaths["cart_checkout_button"]).click()
    logging.info("在結帳頁面輸入 CVC...")
    WebDriverWait(maindriver, 10).until(
        EC.element_to_be_clickable((By.XPATH, xpaths["cvc_input"]))
    )
    maindriver.find_element(By.XPATH, xpaths["cvc_input"]).send_keys(CVC)
    if not DRY_RUN:
        logging.info("點擊「確認付款」...")
        WebDriverWait(maindriver, 10).until(
            EC.element_to_be_clickable((By.XPATH, xpaths["confirm_payment_button"]))
        )
        btn = maindriver.find_element(By.XPATH, xpaths["confirm_payment_button"])
        maindriver.execute_script("arguments[0].click();", btn)
    else:
        logging.info("測試模式 (DRY_RUN=True)，未點擊最後的確認付款按鈕。")


def get_trace_tr_ids(maindriver):
    """
    從追蹤清單頁面擷取所有商品的追蹤 ID。
    """
    row_xpath = '//*[@id="traceData"]/tbody/tr[1]/td/table/tbody/tr'
    rows = maindriver.find_elements(By.XPATH, row_xpath)
    ids = []
    for r in rows:
        rid = r.get_attribute("id") or ""
        if not rid or "tablehead" in rid or "loading" in rid:
            continue
        ids.append(rid)
    return ids


def build_button_api_url(root_ids):
    """
    根據商品根 ID 列表構建查詢商品按鈕狀態的 API URL。
    """
    base = "https://ecapi-cdn.pchome.com.tw/cdn/ecshop/prodapi/v2/prod/button"
    id_param = ",".join(root_ids)
    fields = "Id,ButtonType"
    return f"{base}&id={id_param}&fields={fields}"


def open_new_tab(maindriver, url):
    """
    在新的瀏覽器分頁中打開指定的 URL。
    """
    maindriver.switch_to.new_window("tab")
    maindriver.get(url)
    return maindriver.current_window_handle


def read_json_from_page(maindriver):
    """
    從當前頁面讀取 body 內容並解析為 JSON。
    """
    txt = maindriver.execute_script(
        "return document.body.innerText || document.body.textContent;"
    )
    return json.loads(txt)


def all_for_sale(button_list):
    """
    檢查商品按鈕列表中的所有商品是否都為「ForSale」狀態。
    """
    return all(item.get("ButtonType") == "ForSale" for item in button_list)


def add_all_with_add_cart(maindriver, items):
    """
    將所有指定商品加入購物車。

    流程：
    1. 切換回追蹤清單頁面。
    2. 遍歷商品列表，執行 JavaScript 將每個商品加入購物車。
    3. 監控購物車數量，直到所有商品都成功加入。
    4. 導向購物車頁面。
    """

    logging.info("關閉 API 查詢分頁。")
    maindriver.close()
    trace_handle = maindriver.window_handles[0]
    total_count = len(items)
    logging.info("開始加入購物車，共 %d 件商品", total_count)
    maindriver.switch_to.window(trace_handle)

    for item in items:
        itsno = item.get("Id")
        if not itsno:
            continue
        js = f"ShopCart.addCart({{itsno: '{itsno}', Qty: 1, check: false}});"
        logging.info("加入 %s", itsno)
        maindriver.execute_script(js)
        time.sleep(INTERVAL)
    cart_counter_xpath = "/html/body/div[5]/a/span[2]/a"
    timeout = 10
    start_time = time.time()
    while True:
        try:
            cart_count_text = maindriver.find_element(By.XPATH, cart_counter_xpath).text
            cart_count = int(cart_count_text)
            if cart_count >= total_count:
                logging.info("購物車商品數量達標：%d / %d", cart_count, total_count)
                break
        # pylint: disable=W0718:broad-exception-caught
        except Exception:
            pass
        if time.time() - start_time > timeout:
            logging.warning("等待購物車更新超時")
            break
        time.sleep(0.3)

    logging.info("導向購物車頁面")
    maindriver.get(CART_URL)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={CHROME_PROFILE}")
    driver = webdriver.Chrome(service=ChromeService(), options=options)
    driver.set_page_load_timeout(120)

    logging.info("正在前往追蹤清單，以檢查登入狀態...")
    driver.get(TRACE_LIST_URL)
    if LOGIN_URL_IDENTIFIER in driver.current_url:
        logging.info("偵測到需要登入，請在瀏覽器中手動完成登入...")
        while LOGIN_URL_IDENTIFIER in driver.current_url:
            time.sleep(0.5)
        logging.info("登入成功！")
    else:
        logging.info("檢查完畢，已是登入狀態。")

    time.sleep(2)

    tr_ids = get_trace_tr_ids(driver)
    if not tr_ids:
        logging.info("未找到任何追蹤商品列，結束。")
        driver.quit()
        raise SystemExit(0)

    base_ids = [tid.rsplit("-", 1)[0] if "-" in tid else tid for tid in tr_ids]

    API_URL = build_button_api_url(base_ids)
    open_new_tab(driver, API_URL)

    while True:
        try:
            api_items = read_json_from_page(driver)

            if api_items:
                if all_for_sale(api_items):
                    logging.info("全部 ForSale，回到追蹤分頁送 addCart。")
                    add_all_with_add_cart(driver, api_items)
                    checkout(driver)
                    break
                logging.info("仍有 NotReady，持續重新整理頁面查詢中...")
                time.sleep(INTERVAL)
                driver.refresh()
            else:
                time.sleep(INTERVAL * 5)
                driver.refresh()

        # pylint: disable=W0718:broad-exception-caught
        except Exception as e:
            logging.error("解析或請求錯誤：%s", e)
            time.sleep(INTERVAL)
            driver.refresh()

    time.sleep(100)
