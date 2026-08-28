
from agents.scanner_agent import scan_product_label
from agents.chemist_agent import check_product_conflicts
from firestore_helpers import (
    save_product, get_all_products, save_conflict,
    get_active_conflicts, log_pipeline_event,
)


async def run_shelf_reanalysis_pipeline(image_uri: str, file_name: str):
    """
    Execute the shelf reanalysis cascade.

    Args:
        image_uri: Cloud Storage URI of the uploaded product photo
        file_name: Original filename for logging
    """
    pipeline_name = "shelf_reanalysis"

    try:
        log_pipeline_event(
            pipeline_name,
            f"Cascade triggered by upload: {file_name}"
        )

        # Step 1: Extract ingredients via Gemini Vision
        log_pipeline_event(pipeline_name, "Scanning product label with Gemini Vision...")
        product_data = await scan_product_label(image_uri)
        log_pipeline_event(
            pipeline_name,
            f"Extracted {len(product_data.get('ingredients', []))} ingredients "
            f"from {product_data.get('product_name', 'unknown product')}"
        )

        # Step 2: Mark low-confidence ingredients
        needs_review = [
            i for i in product_data.get("ingredients", [])
            if i.get("needs_review")
        ]
        if needs_review:
            log_pipeline_event(
                pipeline_name,
                f"{len(needs_review)} ingredients need manual review (low OCR confidence)",
                status="warning",
            )

        # Step 3: Save product to shelf
        product_data["photo_uri"] = image_uri
        product_id = save_product(product_data)
        product_data["id"] = product_id
        log_pipeline_event(
            pipeline_name,
            f"Product saved to shelf: {product_data.get('product_name')}"
        )

        # Step 4: Run N×N conflict analysis against ENTIRE shelf
        all_products = get_all_products()
        log_pipeline_event(
            pipeline_name,
            f"Running N×N conflict analysis across {len(all_products)} products..."
        )

        conflicts = check_product_conflicts(all_products)

        # Step 5: Save new conflicts
        # Filter to only conflicts involving the new product
        new_conflicts = [
            c for c in conflicts
            if c["product_a_id"] == product_id or c["product_b_id"] == product_id
        ]

        critical_count = 0
        for conflict in new_conflicts:
            save_conflict(conflict)
            if conflict["severity"] == "critical":
                critical_count += 1

        if new_conflicts:
            log_pipeline_event(
                pipeline_name,
                f"Found {len(new_conflicts)} conflicts ({critical_count} critical) "
                f"involving {product_data.get('product_name')}",
                status="warning" if critical_count == 0 else "error",
            )
        else:
            log_pipeline_event(
                pipeline_name,
                f"No conflicts found — {product_data.get('product_name')} is compatible with your shelf!",
                status="success",
            )

        # Step 6: If critical conflicts found, trigger routine regeneration
        if critical_count > 0:
            log_pipeline_event(
                pipeline_name,
                "Critical conflicts detected — triggering routine regeneration...",
                status="error",
            )
            # Import here to avoid circular imports
            from pipelines.nightly_routine import run_nightly_routine_pipeline
            await run_nightly_routine_pipeline()
            log_pipeline_event(
                pipeline_name,
                "Routines regenerated to account for new conflicts",
                status="success",
            )

        log_pipeline_event(
            pipeline_name,
            f"Shelf reanalysis cascade complete for {product_data.get('product_name')}",
            status="success",
        )

        return {
            "status": "success",
            "product": product_data,
            "conflicts_found": len(new_conflicts),
            "critical_conflicts": critical_count,
        }

    except Exception as e:
        log_pipeline_event(pipeline_name, f"Pipeline failed: {str(e)}", status="error")
        raise