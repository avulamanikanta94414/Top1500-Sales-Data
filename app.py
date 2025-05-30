from flask import Flask, request, render_template, send_file
import pandas as pd
import ast, re, io
from datetime import datetime
import os

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

BARCODE_COLUMN_NAME = "Barcodes"

def find_barcode_column(df):
    if BARCODE_COLUMN_NAME in df.columns:
        return BARCODE_COLUMN_NAME
    if len(df.columns) > 10:
        return df.columns[10]
    raise KeyError("Barcode column not found.")

def parse_items(cell):
    if pd.isna(cell):
        return []
    try:
        parsed = ast.literal_eval(str(cell).strip())
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except Exception:
        pass
    return re.split(r',\s*', str(cell))

def clean_code(item):
    return item.strip().strip('"').strip("'").split(':')[-1].strip()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            # Check if files were uploaded
            if 'top_file' not in request.files or 'sold_file' not in request.files:
                return render_template('index.html', error="Please select both files.")
            
            top_file = request.files['top_file']
            sold_file = request.files['sold_file']
            
            # Check if files were actually selected
            if top_file.filename == '' or sold_file.filename == '':
                return render_template('index.html', error="Please select both files.")
            
            # Read CSV files
            df_top = pd.read_csv(top_file)
            df_sold = pd.read_csv(sold_file)
            
            # Find barcode column
            barcode_col = find_barcode_column(df_top)
            
            # Process barcodes
            all_series = df_top[barcode_col].apply(lambda cell: [clean_code(x) for x in parse_items(cell) if clean_code(x)])
            max_len = int(all_series.str.len().max() or 0)
            
            # Create barcode columns
            for i in range(max_len):
                df_top[f"Code_{i+1}"] = all_series.apply(lambda lst, idx=i: lst[idx] if idx < len(lst) else "")
            
            barcode_columns = [col for col in df_top.columns if col.startswith("Code_")]
            
            # Create barcode to row mapping
            barcode_to_row = {}
            for _, row in df_top.iterrows():
                for bc in [row[col] for col in barcode_columns if row[col]]:
                    barcode_to_row[bc] = row
            
            # Process sold data
            output_data = []
            for _, sold_row in df_sold.iterrows():
                sku = str(sold_row.get("SKU", "")).strip()
                matched_row = barcode_to_row.get(sku)
                
                if matched_row is not None:
                    output_data.append({
                        "Category Group ID": matched_row.get("Category Group ID", ""),
                        "Category Group Name": matched_row.get("Category Group Name", ""),
                        "Brand": matched_row.get("Brand", ""),
                        "Category": matched_row.get("Category", ""),
                        "Qty": sold_row.get("Qty", 0),
                        "In Stock Qty": matched_row.get("In Stock Qty", 0),
                        "Matched Barcode": sku
                    })
                else:
                    output_data.append({
                        "Category Group ID": "Not Available",
                        "Category Group Name": "Not Available",
                        "Brand": "Not Available",
                        "Category": "Not Available",
                        "Qty": sold_row.get("Qty", 0),
                        "In Stock Qty": 0,
                        "Matched Barcode": sku
                    })
            
            # Create output Excel file
            df_output = pd.DataFrame(output_data)
            output = io.BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_output.to_excel(writer, index=False, sheet_name="Matched Output")
            
            output.seek(0)
            filename = f"Matched_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            return send_file(
                output, 
                as_attachment=True, 
                download_name=filename,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
        except Exception as e:
            return render_template('index.html', error=f"An error occurred: {str(e)}")
    
    return render_template('index.html')

@app.errorhandler(413)
def too_large(e):
    return render_template('index.html', error="File too large. Maximum size is 16MB."), 413

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
