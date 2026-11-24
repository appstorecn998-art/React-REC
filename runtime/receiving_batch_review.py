from types import SimpleNamespace

def reviewed_window(sheet,rows,receipt_images,pr_images):
    return SimpleNamespace(current_sheet=sheet,data_by_sheet={sheet:rows},images=receipt_images,receipt_references=lambda:pr_images)
