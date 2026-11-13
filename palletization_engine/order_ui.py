"""
Simple desktop UI to run order prioritization and export the visualization CSV.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
from pathlib import Path

from run_csv import (
    cargar_base_datos,
    construir_pedido_manual,
    ManualOrderValidationError,
    exportar_pedido,
    obtener_lineas_pedido,
    resolver_pedido,
    resolver_pedido_manual,
)
from solution_dashboard import write_solution_dashboard


class OrderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Order Prioritization")
        self.geometry("980x720")
        self.minsize(900, 640)

        self.df = None
        self.peso_max = None
        self.current_result = None
        self.current_text = ""
        self.current_lineas = []
        self.current_pedido_id = ""

        self._build_ui()
        self._load_data_async()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        title = ttk.Label(header, text="Order Prioritization", font=("Segoe UI", 18, "bold"))
        title.grid(row=0, column=0, sticky="w")

        self.status_var = tk.StringVar(value="Loading data...")
        status = ttk.Label(header, textvariable=self.status_var)
        status.grid(row=1, column=0, sticky="w", pady=(4, 0))

        controls = ttk.Frame(self, padding=(16, 0, 16, 12))
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)

        ttk.Label(controls, text="Mode").grid(row=0, column=0, sticky="w")
        self.mode_var = tk.StringVar(value="existing")
        mode_box = ttk.Combobox(
            controls,
            textvariable=self.mode_var,
            values=("existing", "manual"),
            state="readonly",
            width=12,
        )
        mode_box.grid(row=0, column=1, sticky="w", padx=(10, 10))
        mode_box.bind("<<ComboboxSelected>>", self._refresh_mode)

        ttk.Label(controls, text="Order number").grid(row=0, column=2, sticky="w")
        self.order_var = tk.StringVar()
        self.order_entry = ttk.Entry(controls, textvariable=self.order_var)
        self.order_entry.grid(row=0, column=3, sticky="ew", padx=(10, 10))
        self.order_entry.focus_set()

        self.run_button = ttk.Button(controls, text="Run order prioritization", command=self.run_order)
        self.run_button.grid(row=0, column=4, padx=(0, 10))

        self.export_button = ttk.Button(controls, text="Export CSV", command=self.export_csv, state="disabled")
        self.export_button.grid(row=0, column=5)

        self.dashboard_button = ttk.Button(
            controls, text="Open HTML dashboard", command=self.open_dashboard, state="disabled"
        )
        self.dashboard_button.grid(row=0, column=6, padx=(8, 0))

        self.paste_frame = ttk.LabelFrame(self, text="Manual order paste", padding=12)
        self.paste_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.paste_frame.columnconfigure(0, weight=1)

        ttk.Label(
            self.paste_frame,
            text="Paste one line per material. Format: material,cases  Example: 80,50",
        ).grid(row=0, column=0, sticky="w")

        self.paste_text = tk.Text(self.paste_frame, height=6, wrap="none", font=("Consolas", 10))
        self.paste_text.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.paste_text.insert("1.0", "80,50\n81,20\n82,10")
        self.paste_text.configure(state="disabled")

        output_frame = ttk.Frame(self, padding=(16, 0, 16, 16))
        output_frame.grid(row=3, column=0, sticky="nsew")
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)

        self.output = tk.Text(output_frame, wrap="word", font=("Consolas", 10))
        self.output.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=scrollbar.set)

        self._write_output("Enter an order number and click Run order prioritization.\n")

    def _refresh_mode(self, event=None):
        mode = self.mode_var.get()
        if mode == "manual":
            self.order_entry.configure(state="disabled")
            self.paste_text.configure(state="normal")
            self.status_var.set("Manual mode: paste material,cases lines.")
        else:
            self.order_entry.configure(state="normal")
            self.paste_text.configure(state="disabled")
            self.status_var.set("Existing order mode: enter an order number.")

    def _load_data_async(self):
        def worker():
            try:
                self.df, self.peso_max = cargar_base_datos()
                self.after(0, self._on_data_loaded)
            except Exception as exc:
                message = f"Failed to load data: {exc}"
                self.after(0, self._on_error, message)

        threading.Thread(target=worker, daemon=True).start()

    def _on_data_loaded(self):
        self.status_var.set(
            f"Ready. Max mixed-pallet gross weight: {self.peso_max:.1f} kg"
        )
        self.run_button.configure(state="normal")

    def _on_error(self, message: str):
        self.status_var.set(message)
        self.run_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.dashboard_button.configure(state="disabled")
        messagebox.showerror("Error", message)

    def _set_busy(self, busy: bool):
        self.run_button.configure(state="disabled" if busy else "normal")
        self.export_button.configure(state="disabled" if busy or self.current_result is None else "normal")
        self.dashboard_button.configure(state="disabled" if busy or self.current_result is None else "normal")
        self.order_entry.configure(state="disabled" if busy else "normal")

    def _write_output(self, text: str, append: bool = True):
        if not append:
            self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, text)
        self.output.see(tk.END)

    def run_order(self):
        if self.df is None:
            messagebox.showinfo("Loading", "Data is still loading. Please wait a moment.")
            return

        self.current_result = None
        self.current_text = ""
        self.current_lineas = []
        self.current_pedido_id = ""
        self.export_button.configure(state="disabled")
        self._write_output("", append=False)
        mode = self.mode_var.get()
        if mode == "manual":
            self._write_output("Running manual order prioritization...\n\n")
            self.status_var.set("Processing manual order...")
        else:
            pedido_id = self.order_var.get().strip()
            if not pedido_id:
                messagebox.showwarning("Missing order", "Please enter an order number.")
                return
            self._write_output(f"Running order prioritization for {pedido_id}...\n\n")
            self.status_var.set("Processing order...")
        self._set_busy(True)

        def worker():
            try:
                if mode == "manual":
                    texto_manual = self.paste_text.get("1.0", tk.END)
                    resultado, texto, _, lineas = resolver_pedido_manual(
                        texto_manual,
                        df=self.df,
                        peso_max=self.peso_max,
                        usar_3d=True,
                    )
                    if resultado is None:
                        self.after(0, lambda: self._finish_manual_error("No valid manual lines were provided."))
                        return
                    self.after(0, lambda: self._finish_success(resultado, texto, lineas, pedido_label="MANUAL"))
                else:
                    pedido_id = self.order_var.get().strip()
                    resultado, texto, _ = resolver_pedido(pedido_id, df=self.df, peso_max=self.peso_max, usar_3d=True)
                    if resultado is None:
                        self.after(0, lambda: self._finish_no_order(pedido_id))
                        return
                    lineas = obtener_lineas_pedido(self.df, pedido_id)
                    self.after(0, lambda: self._finish_success(resultado, texto, lineas, pedido_label=pedido_id))
            except Exception as exc:
                if isinstance(exc, ManualOrderValidationError):
                    self.after(0, self._confirm_manual_invalid_materials, texto_manual, exc)
                    return
                message = f"Processing failed: {exc}"
                self.after(0, self._on_error, message)

        threading.Thread(target=worker, daemon=True).start()

    def _confirm_manual_invalid_materials(self, texto_manual, error):
        details = "\n".join(
            f"- Material {item['article']}: {item['reason']}"
            for item in error.invalid_materials
        )
        remove = messagebox.askyesno(
            "Invalid manual materials",
            "The following materials cannot be included in this order:\n\n"
            f"{details}\n\n"
            "Remove these materials and continue with the compatible materials?",
            parent=self,
        )
        if not remove:
            self._finish_manual_error(
                "Manual order cancelled: invalid materials were not removed.\n" + details
            )
            return
        self._set_busy(True)
        self.status_var.set("Removing invalid materials and processing the remaining order...")

        def worker():
            try:
                resultado, texto, _, lineas = resolver_pedido_manual(
                    texto_manual,
                    df=self.df,
                    peso_max=self.peso_max,
                    usar_3d=True,
                    skip_invalid_materials={item["article"] for item in error.invalid_materials},
                )
                if resultado is None:
                    self.after(0, self._finish_manual_error, "No compatible manual materials remain.")
                    return
                self.after(0, self._finish_success, resultado, texto, lineas, "MANUAL")
            except Exception as exc:
                message = f"Processing failed after removing invalid materials: {exc}"
                self.after(0, self._on_error, message)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_no_order(self, pedido_id: str):
        self._set_busy(False)
        self.status_var.set("Order not found.")
        self._write_output(f"Pedido {pedido_id} no encontrado.\n")
        messagebox.showinfo("Not found", f"Order {pedido_id} was not found.")

    def _finish_manual_error(self, message: str):
        self._set_busy(False)
        self.status_var.set(message)
        self._write_output(message + "\n")
        messagebox.showerror("Manual order error", message)

    def _finish_success(self, resultado, texto: str, lineas, pedido_label: str):
        self.current_result = resultado
        self.current_text = texto
        self.current_lineas = lineas
        self.current_pedido_id = pedido_label
        self._set_busy(False)
        self.status_var.set("Order processed successfully.")
        self._write_output(texto + "\n")
        self.export_button.configure(state="normal")
        self.dashboard_button.configure(state="normal")

    def open_dashboard(self):
        if self.current_result is None:
            messagebox.showinfo("No solution", "Run an order before opening the dashboard.")
            return
        try:
            output_path = Path.cwd() / f"dashboard_{self.current_pedido_id}.html"
            write_solution_dashboard(self.current_result, output_path, self.current_pedido_id)
            webbrowser.open_new_tab(output_path.resolve().as_uri())
            self.status_var.set(f"Dashboard opened: {output_path}")
            self._write_output(f"\nHTML dashboard opened: {output_path}\n")
        except Exception as exc:
            self._on_error(f"Dashboard failed: {exc}")

    def export_csv(self):
        if self.current_result is None:
            messagebox.showinfo("Nothing to export", "Run an order first.")
            return
        default_name = f"outputs_visualizacion_{self.current_pedido_id}.csv"
        path = filedialog.asksaveasfilename(
            title="Export visualization CSV",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return

        try:
            output_path = exportar_pedido(
                self.current_pedido_id,
                self.current_result,
                self.current_lineas,
                output_path=path,
            )
            self.status_var.set(f"CSV exported to {output_path}")
            self._write_output(f"\nCSV exported to: {output_path}\n")
            messagebox.showinfo("Export complete", f"CSV exported to:\n{output_path}")
        except Exception as exc:
            self._on_error(f"Export failed: {exc}")


def main():
    app = OrderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
