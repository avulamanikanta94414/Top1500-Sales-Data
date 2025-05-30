import pandas as pd
import ast
import re
import os
from datetime import datetime
from flask import Flask, request, render_template, send_file

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

BARCODE_COLUMN_NAME = "Barcodes"


def find_barcode_column(df):
    if BARCODE_COLUMN_NAME in df.columns:
        return BARCODE_COLUMN_NAME
    if len(df.columns) > 10:
        return df.columns[10]
    raise KeyError("Could not find barcode column")


def parse_items(cell):
    if pd.isna(cell):
        return []
    text = str(cell).strip()
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except Exception:
        pass
    return re.split(r',\s*', text)


def clean_code(item):
    item_str = item.strip().strip('"').strip("'")
    return item_str.split(':')[-1].strip()


def split_barcodes(df):
    barcode_col = find_barcode_column(df)
    all_series = df[barcode_col].apply(lambda cell: [clean_code(x) for x in parse_items(cell) if clean_code(x)])
    max_len = int(all_series.str.len().max() or 0)
    for i in range(max_len):
        df[f"Code_{i + 1}"] = all_series.apply(lambda lst, idx=i: lst[idx] if idx < len(lst) else "")
    return df


def generate_report(top1500_file, product_sold_file, instock_file):
    df_top = pd.read_excel(top1500_file)
    df_top = split_barcodes(df_top)

    df_sold = pd.read_csv(product_sold_file)
    df_stock = pd.read_csv(instock_file)

    df_sold = df_sold.merge(df_stock[["SKU", "Barcode"]], on="SKU", how="left")

    all_codes = df_top[[col for col in df_top.columns if col.startswith("Code_")]]
    code_map = {}

    for idx, row in df_top.iterrows():
        for code in all_codes.loc[idx]:
            if code:
                code_map[code] = row

    report_rows = []
    for idx, row in df_sold.iterrows():
        bc = row['Barcode']
        matched_row = code_map.get(str(bc))
        if matched_row is not None:
            report_rows.append({
                'Category Group ID': matched_row.get('Category Group ID', ""),
                'Name': matched_row.get('Name', ""),
                'Brand': matched_row.get('Brand', ""),
                'Category': matched_row.get('Category', ""),
                'Qty': row.get('Qty', 0),
                'In Stock Qty': df_stock[df_stock['Barcode'] == bc]['InStockQty'].values[0] if bc in df_stock['Barcode'].values else "Not Available",
                'Matched Barcode': bc
            })
        else:
            report_rows.append({
                'Category Group ID': "",
                'Name': "",
                'Brand': "",
                'Category': "",
                'Qty': 0,
                'In Stock Qty': "Not Available",
                'Matched Barcode': bc
            })

    df_result = pd.DataFrame(report_rows)
    now_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    output_path = os.path.join(OUTPUT_FOLDER, f"Final_Report_{now_str}.xlsx")
    df_result.to_excel(output_path, index=False)
    return output_path


@app.route('/', methods=['GET', 'POST'])
def upload_files():
    if request.method == 'POST':
        top1500 = request.files['top1500']
        sold = request.files['productsold']
        stock = request.files['instock']

        top1500_path = os.path.join(UPLOAD_FOLDER, top1500.filename)
        sold_path = os.path.join(UPLOAD_FOLDER, sold.filename)
        stock_path = os.path.join(UPLOAD_FOLDER, stock.filename)

        top1500.save(top1500_path)
        sold.save(sold_path)
        stock.save(stock_path)

        output_file = generate_report(top1500_path, sold_path, stock_path)
        return send_file(output_file, as_attachment=True)

    return '''
    <!doctype html>
    <title>Barcode Report Generator</title>
    <h1>Upload Files</h1>
    <form method=post enctype=multipart/form-data>
      Top1500 Excel: <input type=file name=top1500><br><br>
      ProductSold CSV: <input type=file name=productsold><br><br>
      InStock CSV: <input type=file name=instock><br><br>
      <input type=submit value=Generate>
    </form>
    '''


if __name__ == '__main__':
    app.run(debug=True)
