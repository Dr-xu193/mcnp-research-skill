# -*- coding: utf-8 -*-
"""
MCNP 综合效率刻度与能谱分析平台 V9.0 (实体封装源架构 - 修复注入截断)
功能集成：
1. 模块 A: MPI 仿真调度，支持实体封装源 (TR1) 的三维整体平移与 (Co-60/Na-22/Ba-133) 复合源模式
2. 模块 B: Matplotlib 能谱深度对比与单/多谱出图
3. 模块 C: GEB 参数反推、智能文件名嗅探、多峰并发提取与实验规范效率积分
"""
import os
import re
import csv
import glob
import shutil
import time
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
import warnings
import math
from datetime import datetime

# 解决画图乱码及负号问题
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False 
warnings.filterwarnings("ignore", category=UserWarning)


class SpectraEngine:
    @staticmethod
    def load_data(file_path):
        """解析CSV并提取能量与计数数据"""
        try:
            df = pd.read_csv(file_path)
            df.columns = df.columns.str.strip()
            
            x_cols = [c for c in df.columns if 'energy' in c.lower() or 'mev' in c.lower()]
            y_cols = [c for c in df.columns if 'tally' in c.lower() or 'count' in c.lower()]
            
            x_data = df[x_cols[0]] if x_cols else df.iloc[:, 0]
            y_data = df[y_cols[0]] if y_cols else df.iloc[:, 1]
            
            label = os.path.splitext(os.path.basename(file_path))[0]
            cm_idx = label.lower().find('cm')
            if cm_idx != -1:
                label = label[:cm_idx+2]
            
            return label, x_data, y_data
        except Exception as e:
            raise ValueError(f"文件读取失败: {str(e)}")

    @staticmethod
    def generate_plot(data_list, output_path):
        """生成线性与对数对比图"""
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
        colors = ['#1f77b4', '#d62728', '#2ca02c', '#9467bd', '#8c564b', '#e377c2']

        for i, (label, x, y) in enumerate(data_list):
            c = colors[i % len(colors)]
            axes[0].plot(x, y, label=label, color=c, lw=1.5, alpha=0.8)
            axes[1].semilogy(x, y, label=label, color=c, lw=1.5, alpha=0.8)

        max_x_valid = []
        for _, x, y in data_list:
            valid_x = x[y > 0]
            if not valid_x.empty:
                max_x_valid.append(valid_x.max())
                
        plot_max_x = max(max_x_valid) if max_x_valid else 1.6
        max_y = max([y.max() for _, _, y in data_list]) if data_list else 1.0

        for ax in axes:
            ax.set_xlabel('Energy (MeV)', fontsize=12)
            ax.set_ylabel('Tally (Counts/Particle)', fontsize=12)
            ax.legend(loc='upper right')
            ax.grid(True, linestyle=':', alpha=0.6)
            ax.set_xlim(left=0, right=plot_max_x * 1.05) 
        
        axes[0].set_title('Gamma Spectra (Linear Scale)', fontsize=14)
        axes[0].set_ylim(bottom=0, top=max_y * 1.05)
        axes[1].set_title('Gamma Spectra (Log Scale)', fontsize=14)
        axes[1].set_ylim(bottom=max_y * 1e-6, top=max_y * 2.5) 
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close(fig)

class MCNPPlatformApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MCNP 综合效率刻度与能谱分析平台 V9.0 (实体封装源架构)")
        self.root.geometry("1050x900")
        self.root.minsize(950, 750)

        style = ttk.Style()
        try: style.theme_use('clam')
        except: pass
        bg_color = "#F0F2F5"
        self.root.configure(bg=bg_color)
        
        style.configure(".", background=bg_color, font=("Microsoft YaHei", 10))
        style.configure("TNotebook", background=bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", padding=[20, 10], font=("Microsoft YaHei", 11, "bold"), background="#E0E0E0")
        style.map("TNotebook.Tab", background=[("selected", "#FFFFFF")], foreground=[("selected", "#0078D7")])
        style.configure("TLabelframe", background="#FFFFFF", borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", font=("Microsoft YaHei", 11, "bold"), foreground="#0078D7", background="#FFFFFF")

        self.notebook = ttk.Notebook(self.root)
        self.tab_sim = ttk.Frame(self.notebook)
        self.tab_plot = ttk.Frame(self.notebook)
        self.tab_geb = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_sim, text="  模块 A: MCNP 全自动仿真  ")
        self.notebook.add(self.tab_plot, text="  模块 B: 能谱探测对比出图  ")
        self.notebook.add(self.tab_geb, text="  模块 C: 智能特征提取与 GEB 反推  ")
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ===========================
        # 初始化 模块 A 变量
        # ===========================
        self.font_main = ("Microsoft YaHei", 9)
        self.font_bold = ("Microsoft YaHei", 9, "bold")
        self.font_title = ("Microsoft YaHei", 10, "bold")
        
        self.energy_dict = {
            "Am-241 (59.5 keV)": 0.0595,
            "Ba-133 (81 keV)": 0.081,
            "Ba-133 (356 keV)": 0.356,
            "Cs-137 (662 keV)": 0.662,
            "Co-60 (1173 keV)": 1.173,
            "Co-60 (1332 keV)": 1.332
        }

        self.reference_dict = {
            "探测器铝壳表面 (Z = -0.34 cm)": {"z": -0.34, "short": "铝壳表面"},
            "NaI 晶体前表面 (Z = 0.00 cm)": {"z": 0.00, "short": "晶体表面"},
            "NaI 晶体几何中心 (Z = 3.81 cm)": {"z": 3.81, "short": "几何中心"}
        }

        self.base_file = tk.StringVar(value="b.txt")
        self.out_dir = tk.StringVar(value="默认: 与基础文件同目录")
        self.dist_val = tk.StringVar(value="20")
        self.ref_val = tk.StringVar(value="NaI 晶体几何中心 (Z = 3.81 cm)")
        self.mpi_cmd_var = tk.StringVar(value="mpirun -np 17 mcnp5mpi.exe")
        self.nps_var = tk.StringVar(value="10000000")
        
        self.energy_vars = {name: tk.BooleanVar(value=True) for name in self.energy_dict}
        self.custom_energy_var = tk.BooleanVar(value=False)
        self.custom_energy_val = tk.StringVar(value="0.500")

        self.co60_composite_var = tk.BooleanVar(value=False)
        self.na22_composite_var = tk.BooleanVar(value=False)
        self.ba133_composite_var = tk.BooleanVar(value=False)

        self.geb_enable_var = tk.BooleanVar(value=False)
        self.geb_a_val = tk.StringVar(value="-0.00789")
        self.geb_b_val = tk.StringVar(value="0.06769")
        self.geb_c_val = tk.StringVar(value="0.21159")
        
        self.is_running = False

        # ===========================
        # 初始化 模块 B 变量
        # ===========================
        self.file1_path = tk.StringVar()
        self.file2_path = tk.StringVar()
        self.mode = tk.IntVar(value=1)

        # ===========================
        # 初始化 模块 C 变量 (GEB 反推)
        # ===========================
        self.geb_ref_txt_path = ""
        self.geb_ref_params = None
        self.geb_csv_files = [] 
        self.geb_data_points = []
        self.M_E_C2 = 0.511

        # SP2 权重（与 excel.py NUCLIDE_BRANCHES 及 compare.py SP2_WEIGHTS 统一）
        self.sp2_weights = {
            'CO-60':  {1.173: 0.9985, 1.332: 0.9998},
            'CS-137': {0.662: 0.851},
            'NA-22':  {0.511: 1.798, 1.274: 0.9994},
            'BA-133': {0.081: 0.329, 0.276: 0.071, 0.303: 0.183, 0.356: 0.6205, 0.384: 0.089},
            'AM-241': {0.0595: 0.359}
        }

        self.setup_ui_sim()
        self.setup_ui_plot()
        self.setup_ui_geb()

    def setup_ui_sim(self):
        container = self.tab_sim
        pad = {'padx': 10, 'pady': 5}
        
        self.paned = ttk.PanedWindow(container, orient=tk.VERTICAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        top_pane = ttk.Frame(self.paned)
        self.paned.add(top_pane, weight=3) 
        self.bottom_pane = ttk.Frame(self.paned)
        self.paned.add(self.bottom_pane, weight=2) 
        
        main_canvas = tk.Canvas(top_pane, bg="#FFFFFF", highlightthickness=0)
        scrollbar = ttk.Scrollbar(top_pane, orient="vertical", command=main_canvas.yview)
        scrollable_frame = ttk.Frame(main_canvas)

        canvas_window = main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        scrollable_frame.bind("<Configure>", lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all")))
        main_canvas.bind("<Configure>", lambda e: main_canvas.itemconfig(canvas_window, width=e.width))
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        def _on_mousewheel(event):
            if str(self.notebook.select()) == str(self.tab_sim):
                try:
                    if event.widget.winfo_class() not in ("Text", "TCombobox", "Listbox"):
                        main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                except Exception: pass
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        f1 = tk.LabelFrame(scrollable_frame, text=" 1. 核心算力与 I/O 路径 ", font=self.font_title)
        f1.pack(fill="x", padx=10, pady=5)
        tk.Label(f1, text="基础模型 (.txt):", font=self.font_main).grid(row=0, column=0, sticky="w", **pad)
        tk.Entry(f1, textvariable=self.base_file, width=45, font=self.font_main).grid(row=0, column=1, **pad)
        tk.Button(f1, text="浏览...", font=self.font_main, command=lambda: self.base_file.set(filedialog.askopenfilename())).grid(row=0, column=2, **pad)
        tk.Label(f1, text="项目工作目录:", font=self.font_main).grid(row=1, column=0, sticky="w", **pad)
        tk.Entry(f1, textvariable=self.out_dir, width=45, font=self.font_main).grid(row=1, column=1, **pad)
        tk.Button(f1, text="选择...", font=self.font_main, command=lambda: self.out_dir.set(filedialog.askdirectory())).grid(row=1, column=2, **pad)
        tk.Label(f1, text="MPI 启动指令:", font=self.font_main).grid(row=2, column=0, sticky="w", **pad)
        tk.Entry(f1, textvariable=self.mpi_cmd_var, width=45, fg="blue", font=self.font_main).grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        tk.Label(f1, text="NPS (粒子数):", font=self.font_main).grid(row=3, column=0, sticky="w", **pad)
        ttk.Combobox(f1, textvariable=self.nps_var, values=["10000000 (10^7)", "1000000 (10^6)", "100000 (10^5)", "100000000 (10^8)", "1e6"], width=42, font=self.font_main).grid(row=3, column=1, columnspan=2, sticky="w", **pad)

        f2 = tk.LabelFrame(scrollable_frame, text=" 2. 空间几何测量基准 (绑定源中心系) ", font=self.font_title)
        f2.pack(fill="x", padx=10, pady=5)
        ttk.Combobox(f2, textvariable=self.ref_val, values=list(self.reference_dict.keys()), width=45, state="readonly", font=self.font_main).grid(row=0, column=1, columnspan=2, sticky="w", **pad)
        tk.Label(f2, text="卡尺读数 D (cm):", font=self.font_main).grid(row=1, column=0, sticky="w", **pad)
        tk.Entry(f2, textvariable=self.dist_val, width=15, font=self.font_main).grid(row=1, column=1, sticky="w", **pad)

        f3 = tk.LabelFrame(scrollable_frame, text=" 3. 放射源特征峰配置 ", font=self.font_title)
        f3.pack(fill="x", padx=10, pady=5)
        
        for i, name in enumerate(self.energy_dict):
            tk.Checkbutton(f3, text=name, variable=self.energy_vars[name], font=self.font_main).grid(row=i//2, column=i%2, sticky="w", padx=15, pady=2)
        tk.Frame(f3, height=2, bd=1, relief="sunken").grid(row=4, column=0, columnspan=2, sticky="ew", pady=5)
        
        comp_frame = ttk.Frame(f3)
        comp_frame.grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=2)
        ttk.Label(comp_frame, text="✨ 真实复合源模拟 (自动封装 MCNP si/sp 多分支):", font=self.font_bold, foreground="#d32f2f").pack(anchor="w")
        tk.Checkbutton(comp_frame, text="Co-60 (1.17, 1.33 MeV 级联)", variable=self.co60_composite_var, fg="#d32f2f", font=self.font_bold).pack(anchor="w", padx=10)
        tk.Checkbutton(comp_frame, text="Na-22 (0.511 湮灭, 1.274 MeV 级联)", variable=self.na22_composite_var, fg="#d32f2f", font=self.font_bold).pack(anchor="w", padx=10)
        tk.Checkbutton(comp_frame, text="Ba-133 (81k, 276k, 303k, 356k, 384k 复合)", variable=self.ba133_composite_var, fg="#d32f2f", font=self.font_bold).pack(anchor="w", padx=10)
        tk.Frame(f3, height=2, bd=1, relief="sunken").grid(row=6, column=0, columnspan=2, sticky="ew", pady=5)

        f3_custom = tk.Frame(f3)
        f3_custom.grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=2)
        tk.Checkbutton(f3_custom, text="🔨 自定义单能射线 (MeV):", variable=self.custom_energy_var, fg="#0277BD", font=self.font_bold).pack(side="left")
        tk.Entry(f3_custom, textvariable=self.custom_energy_val, width=15, font=self.font_main).pack(side="left", padx=5)

        f_geb = tk.LabelFrame(scrollable_frame, text=" 3.5 探测器能量展宽 (FT8 GEB) 参数 ", font=self.font_title)
        f_geb.pack(fill="x", padx=10, pady=5)
        tk.Checkbutton(f_geb, text="启用 FT8 GEB 卡片 (绘制平滑的高斯能谱图时勾选，计算纯计数率时请勿勾选)", 
                       variable=self.geb_enable_var, font=self.font_bold, fg="#E65100", command=self.toggle_geb).grid(row=0, column=0, columnspan=6, sticky="w", padx=10, pady=(5,0))

        self.geb_presets = {
            "高精度宽能区 (推荐, R_662≈7.7%)": ("-0.00789", "0.06769", "0.21159"),
            "标准通用基准 (简化, R_662≈7.5%)": ("0.0", "0.061", "0.0"),
            "优质晶体模型 (极佳, R_662≈6.8%)": ("0.0", "0.055", "0.0"),
            "老化晶体模型 (劣化, R_662≈10%)": ("0.01", "0.07", "0.0"),
            "手动输入参数 (自定义)": ("", "", "")
        }
        self.geb_preset_var = tk.StringVar(value=list(self.geb_presets.keys())[0])

        tk.Label(f_geb, text="快捷预设:", font=self.font_main).grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.geb_combo = ttk.Combobox(f_geb, textvariable=self.geb_preset_var, values=list(self.geb_presets.keys()), width=35, state="disabled", font=self.font_main)
        self.geb_combo.grid(row=1, column=1, columnspan=5, sticky="w", pady=5)
        self.geb_combo.bind("<<ComboboxSelected>>", self.on_geb_preset_change)

        tk.Label(f_geb, text="a:", font=self.font_main).grid(row=2, column=0, sticky="e")
        self.entry_a = tk.Entry(f_geb, textvariable=self.geb_a_val, width=10, state="disabled")
        self.entry_a.grid(row=2, column=1, sticky="w", padx=2, pady=5)
        tk.Label(f_geb, text="b:", font=self.font_main).grid(row=2, column=2, sticky="e")
        self.entry_b = tk.Entry(f_geb, textvariable=self.geb_b_val, width=10, state="disabled")
        self.entry_b.grid(row=2, column=3, sticky="w", padx=2, pady=5)
        tk.Label(f_geb, text="c:", font=self.font_main).grid(row=2, column=4, sticky="e")
        self.entry_c = tk.Entry(f_geb, textvariable=self.geb_c_val, width=10, state="disabled")
        self.entry_c.grid(row=2, column=5, sticky="w", padx=2, pady=5)

        tk.Button(f_geb, text="🔍 从实验 SPE 谱自动推导真实 GEB 参数", bg="#E65100", fg="white", font=self.font_bold, command=self.extract_geb_from_spe).grid(row=3, column=0, columnspan=6, sticky="ew", padx=10, pady=(5, 5))

        btn_frame = tk.LabelFrame(scrollable_frame, text=" 4. 核心调度中心 ", font=self.font_title)
        btn_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(btn_frame, text="🚀 [一键全自动] 顺序执行：步二(计算) -> 步三(解析) -> 步四(出图)", 
                  bg="#C62828", fg="white", font=("Microsoft YaHei", 12, "bold"), command=self.start_auto_pipeline).pack(fill="x", padx=10, pady=(10, 5))

        sub_btn_frame = tk.Frame(btn_frame)
        sub_btn_frame.pack(fill="x", padx=10, pady=(5, 10))
        tk.Button(sub_btn_frame, text="[步一] 生成输入", bg="#2E7D32", fg="white", font=self.font_bold, command=self.generate_inputs).pack(side="left", fill="x", expand=True, padx=3)
        tk.Button(sub_btn_frame, text="[步二] MPI 计算", bg="#1565C0", fg="white", font=self.font_bold, command=self.start_mpi_execution).pack(side="left", fill="x", expand=True, padx=3)
        tk.Button(sub_btn_frame, text="[步三] 剥离 CSV", bg="#E65100", fg="white", font=self.font_bold, command=self.start_extract_csv).pack(side="left", fill="x", expand=True, padx=3)
        tk.Button(sub_btn_frame, text="[步四] Origin作图", bg="#6A1B9A", fg="white", font=self.font_bold, command=self.start_origin_automation).pack(side="left", fill="x", expand=True, padx=3)

        log_frame = ttk.LabelFrame(self.bottom_pane, text=" 5. 系统实时输出控制台 ", padding=5)
        log_frame.pack(fill="both", expand=True) 
        self.log_box = tk.Text(log_frame, bg="#1E1E1E", fg="#4AF626", font=("Consolas", 11), height=10, borderwidth=0, highlightthickness=0)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=log_scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    def setup_ui_plot(self):
        container = self.tab_plot
        main_frame = ttk.Frame(container, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        mode_frame = ttk.LabelFrame(main_frame, text=" 对比模式选择 ", padding="10")
        mode_frame.pack(fill=tk.X, pady=5)
        ttk.Radiobutton(mode_frame, text="单谱探针 (单文件处理)", variable=self.mode, value=1, command=self._toggle_plot_inputs).pack(side=tk.LEFT, padx=20)
        ttk.Radiobutton(mode_frame, text="双谱镜像 (双文件对比)", variable=self.mode, value=2, command=self._toggle_plot_inputs).pack(side=tk.LEFT, padx=20)

        file_frame = ttk.LabelFrame(main_frame, text=" CSV 数据源配置 ", padding="15")
        file_frame.pack(fill=tk.X, pady=10)

        f1_row = ttk.Frame(file_frame)
        f1_row.pack(fill=tk.X, pady=5)
        ttk.Label(f1_row, text="主曲线源 (A):").pack(side=tk.LEFT)
        ttk.Entry(f1_row, textvariable=self.file1_path, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        tk.Button(f1_row, text="选择文件", font=("Microsoft YaHei", 9), command=lambda: self._select_file_plot(1)).pack(side=tk.LEFT)

        self.f2_row = ttk.Frame(file_frame)
        self.f2_row.pack(fill=tk.X, pady=5)
        ttk.Label(self.f2_row, text="副曲线源 (B):").pack(side=tk.LEFT)
        self.ent_f2 = ttk.Entry(self.f2_row, textvariable=self.file2_path, width=50)
        self.ent_f2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.btn_f2 = tk.Button(self.f2_row, text="选择文件", font=("Microsoft YaHei", 9), command=lambda: self._select_file_plot(2))
        self.btn_f2.pack(side=tk.LEFT)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=30)
        self.btn_merge = tk.Button(btn_frame, text="生成合并对比图", bg="#0277BD", fg="white", font=("Microsoft YaHei", 11, "bold"), command=self._handle_merge, height=2)
        self.btn_merge.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)
        self.btn_sep = tk.Button(btn_frame, text="逐个生成独立图", bg="#2E7D32", fg="white", font=("Microsoft YaHei", 11, "bold"), command=self._handle_separate, height=2)
        self.btn_sep.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)

        info_frame = ttk.LabelFrame(main_frame, text=" 系统补充说明 ", padding="15")
        info_frame.pack(fill=tk.X, pady=10)
        ttk.Label(info_frame, text="注意：\n在模块 A 中提取出的 *_Data.csv 文件均可直接在此导入用于生成高定能谱对比图。").pack(anchor="w")
        self._toggle_plot_inputs()

    def setup_ui_geb(self):
        container = self.tab_geb
        frame_ref = ttk.LabelFrame(container, text=" 1. 基准参数文件 (25.txt) ", padding=5)
        frame_ref.pack(fill=tk.X, padx=10, pady=5)
        self.lbl_geb_ref_path = ttk.Label(frame_ref, text="未选择参考文件...", foreground="gray")
        self.lbl_geb_ref_path.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.X, expand=True)
        btn_load_ref = ttk.Button(frame_ref, text="选择TXT文件", command=self.load_geb_reference_file)
        btn_load_ref.pack(side=tk.RIGHT, padx=10, pady=10)

        frame_csv = ttk.LabelFrame(container, text=" 2. 智能能谱数据源 (系统自动解析提取区间，双击列表项可微调) ", padding=5)
        frame_csv.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        toolbar = ttk.Frame(frame_csv)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        btn_add_csv = ttk.Button(toolbar, text="➕ 添加 CSV 文件", command=self.add_geb_csv_files)
        btn_add_csv.pack(side=tk.LEFT, padx=5)
        btn_del_csv = ttk.Button(toolbar, text="➖ 移除选中文件", command=self.remove_geb_selected_csv)
        btn_del_csv.pack(side=tk.LEFT, padx=5)
        ttk.Label(toolbar, text="*提示: 包含 Composite 关键字的文件名会自动划定多重提取区间", foreground="gray").pack(side=tk.LEFT, padx=20)

        columns = ("FileName", "Path", "PeakRanges")
        self.geb_tree = ttk.Treeview(frame_csv, columns=columns, show="headings", height=6)
        self.geb_tree.heading("FileName", text="文件名")
        self.geb_tree.heading("Path", text="完整路径")
        self.geb_tree.heading("PeakRanges", text="寻峰范围 (自动分配)")
        self.geb_tree.column("FileName", width=180)
        self.geb_tree.column("Path", width=300)
        self.geb_tree.column("PeakRanges", width=400, anchor=tk.W)
        self.geb_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.geb_tree.bind("<Double-1>", self.on_geb_tree_double_click)

        frame_action = ttk.Frame(container)
        frame_action.pack(fill=tk.X, padx=10, pady=5)
        btn_run = ttk.Button(frame_action, text="🚀 一键执行: 多峰并发提取 + 效率积分 + GEB反推", command=self.run_geb_analysis)
        btn_run.pack(side=tk.LEFT, pady=5)
        btn_clear = ttk.Button(frame_action, text="🗑️ 清空报告区", command=lambda: self.geb_report_box.delete(1.0, tk.END))
        btn_clear.pack(side=tk.RIGHT, pady=5)

        self.geb_report_box = scrolledtext.ScrolledText(container, wrap=tk.WORD, font=("Consolas", 10), bg="#1E1E1E", fg="#4AF626")
        self.geb_report_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    def extract_geb_from_spe(self):
        filepaths = filedialog.askopenfilenames(title="选择 SPE 文件以拟合 GEB 参数 (请多选)", filetypes=[("SPE Files", "*.spe")])
        if not filepaths: return

        calib_429 = {'a': -118.408, 'b': 2.279,  'c': -0.000349306}
        calib_430 = {'a': -16.2993, 'b': 1.8952, 'c':  6.08347e-05}
        
        nuclide_energies = {
            'CO-60': [1.173, 1.332],
            'CS-137': [0.662],
            'NA-22': [0.511, 1.274],
            'BA-133': [0.081, 0.276, 0.303, 0.356, 0.384],
            'AM-241': [0.0595]
        }

        energy_fwhm_pairs = []

        self.log_box.config(state="normal")
        self.log("\n" + "="*40 + "\n[*] 启动 SPE 智能 GEB 参数反推...")

        for path in filepaths:
            filename = os.path.basename(path).upper()
            
            # Identify nuclide
            nuc = None
            for key in nuclide_energies:
                parts = key.split('-')
                if parts[0] in filename and parts[1] in filename:
                    nuc = key
                    break
            if not nuc:
                self.log(f"  [跳过] 无法从文件名识别核素: {filename}")
                continue
                
            # Parse SPE
            spec = []
            meas_date = None
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                for i, line in enumerate(lines):
                    line = line.strip()
                    if line == '$DATE_MEA:':
                        meas_date = datetime.strptime(lines[i+1].strip(), '%m/%d/%Y %H:%M:%S')
                    elif line == '$DATA:':
                        start, end = map(int, lines[i+1].split())
                        spec = [int(l.strip()) for l in lines[i+2:i+2+end-start+1]]
                        break
            except Exception as e:
                self.log(f"  [失败] 读取 {filename} 失败: {e}")
                continue

            if not spec: continue
            
            # Determine calibration
            is_apr30 = False
            if meas_date and meas_date.day == 30: is_apr30 = True
            elif '4-30' in filename or '4.30' in filename: is_apr30 = True
            
            cal = calib_430 if is_apr30 else calib_429
            a, b, c = cal['a'], cal['b'], cal['c']
            date_str = "4月30日" if is_apr30 else "4月29日"
            
            self.log(f"  -> 解析 {filename} | 日期路由: {date_str} | 核素: {nuc}")

            # Extract FWHM for each peak
            for e_mev in nuclide_energies[nuc]:
                e_kev = e_mev * 1000.0
                
                # Find theoretical channel
                if c == 0:
                    center_ch = int((e_kev - a) / b) if b != 0 else 512
                else:
                    delta = b**2 - 4*c*(a - e_kev)
                    center_ch = int((-b + math.sqrt(delta)) / (2*c)) if delta > 0 else 512
                center_ch = max(0, min(len(spec)-1, center_ch))

                # Search actual peak top
                l_s = max(0, center_ch - 15)
                r_s = min(len(spec)-1, center_ch + 15)
                peak_slice = spec[l_s:r_s+1]
                if not peak_slice: continue
                
                real_center_ch = l_s + peak_slice.index(max(peak_slice))
                max_counts = spec[real_center_ch]
                half_max = max_counts / 2.0
                
                # Find left FWHM point
                l_fwhm_ch = real_center_ch
                while l_fwhm_ch > 0 and spec[l_fwhm_ch] > half_max:
                    l_fwhm_ch -= 1
                
                # Find right FWHM point
                r_fwhm_ch = real_center_ch
                while r_fwhm_ch < len(spec) - 1 and spec[r_fwhm_ch] > half_max:
                    r_fwhm_ch += 1
                    
                fwhm_channels = r_fwhm_ch - l_fwhm_ch
                
                # Convert FWHM to MeV using derivative dE/dCh = b + 2*c*Ch
                dE_dCh = b + 2 * c * real_center_ch
                fwhm_mev = (fwhm_channels * dE_dCh) / 1000.0
                
                # Filter out bad points (e.g., FWHM too small or too large)
                if 0.001 < fwhm_mev < 0.2:
                    energy_fwhm_pairs.append((e_mev, fwhm_mev))
                    self.log(f"    [√] {e_mev:.3f} MeV 峰提取成功: FWHM={fwhm_mev:.5f} MeV")
                else:
                    self.log(f"    [!] {e_mev:.3f} MeV 峰提取异常 (FWHM={fwhm_mev:.5f} MeV)，跳过")

        if len(energy_fwhm_pairs) < 3:
            self.log("[失败] 提取的有效能量峰少于 3 个，无法进行 GEB 拟合。请选中更多的 SPE 文件。")
            self.log_box.config(state="disabled")
            messagebox.showwarning("拟合失败", "提取的有效峰少于 3 个！MCNP 的 GEB 公式需要至少 3 个点。请多选几个文件。")
            return

        # Fit GEB
        def geb_func(E, A, B, C):
            return A + B * np.sqrt(np.maximum(0, E + C * E**2))

        E_data = np.array([p[0] for p in energy_fwhm_pairs])
        FWHM_data = np.array([p[1] for p in energy_fwhm_pairs])

        try:
            popt, pcov = curve_fit(geb_func, E_data, FWHM_data, bounds=([-1, 0, -1], [1, 1, 10]))
            fit_A, fit_B, fit_C = popt
            
            self.log(f"\n[拟合成功] 使用 {len(E_data)} 个能量点拟合出真实 GEB 参数：")
            self.log(f"  A = {fit_A:.5f}")
            self.log(f"  B = {fit_B:.5f}")
            self.log(f"  C = {fit_C:.5f}")
            
            # Update UI
            self.geb_preset_var.set("手动输入参数 (自定义)")
            self.entry_a.config(state="normal")
            self.entry_b.config(state="normal")
            self.entry_c.config(state="normal")
            
            self.geb_a_val.set(f"{fit_A:.5f}")
            self.geb_b_val.set(f"{fit_B:.5f}")
            self.geb_c_val.set(f"{fit_C:.5f}")
            
            self.geb_enable_var.set(True)
            self.toggle_geb()
            
            messagebox.showinfo("成功", "已成功从 SPE 文件中提取并拟合出真实 GEB 参数，并已填入界面！")
            
        except Exception as e:
            self.log(f"\n[拟合错误] {e}")
            messagebox.showerror("错误", f"拟合过程中出错: {e}")
            
        self.log_box.config(state="disabled")

    def toggle_geb(self):
        state = "normal" if self.geb_enable_var.get() else "disabled"
        c_state = "readonly" if self.geb_enable_var.get() else "disabled"
        self.geb_combo.config(state=c_state)
        if self.geb_preset_var.get() == "手动输入参数 (自定义)" and self.geb_enable_var.get():
            self.entry_a.config(state="normal"); self.entry_b.config(state="normal"); self.entry_c.config(state="normal")
        else:
            self.entry_a.config(state=state); self.entry_b.config(state=state); self.entry_c.config(state=state)

    def on_geb_preset_change(self, event=None):
        preset = self.geb_preset_var.get()
        if preset == "手动输入参数 (自定义)":
            self.entry_a.config(state="normal"); self.entry_b.config(state="normal"); self.entry_c.config(state="normal")
        elif preset in self.geb_presets:
            a, b, c = self.geb_presets[preset]
            self.entry_a.config(state="normal"); self.entry_b.config(state="normal"); self.entry_c.config(state="normal")
            self.geb_a_val.set(a); self.geb_b_val.set(b); self.geb_c_val.set(c)
            self.entry_a.config(state="readonly"); self.entry_b.config(state="readonly"); self.entry_c.config(state="readonly")

    def log(self, text):
        self.log_box.config(state="normal")
        self.log_box.insert(tk.END, text + "\n")
        self.log_box.see(tk.END)
        self.log_box.config(state="disabled")

    def _get_target_dir(self):
        target = self.out_dir.get()
        if "默认" in target or not target.strip(): 
            return os.path.dirname(os.path.abspath(self.base_file.get()))
        return target

    def generate_inputs(self):
        self.log_box.config(state="normal")
        self.log_box.delete(1.0, tk.END)
        target_dir = self._get_target_dir()
        
        raw_nps = self.nps_var.get().strip().split()[0]
        try:
            distance = float(self.dist_val.get())
            ref_full_string = self.ref_val.get()
            z_str = f"{(self.reference_dict[ref_full_string]['z'] - distance):.4f}"
            with open(self.base_file.get(), 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
            content, n_nps = re.subn(r'(?i)^nps\s+.*$', f"nps {raw_nps}", content, flags=re.MULTILINE)
            if n_nps == 0: content += f"\nnps {raw_nps}\n"
        except Exception as e:
            messagebox.showerror("读取错误", str(e))
            return

        geb_pattern = r'(?i)^ft8\s+geb.*$'
        if self.geb_enable_var.get():
            a = self.geb_a_val.get().strip(); b = self.geb_b_val.get().strip(); c = self.geb_c_val.get().strip()
            geb_str = f"FT8 GEB {a} {b} {c}"
            if re.search(geb_pattern, content, flags=re.MULTILINE):
                content = re.sub(geb_pattern, geb_str, content, flags=re.MULTILINE)
            else:
                content, n_e8 = re.subn(r'(?i)^(e8\s+.*)$', r'\1\n' + geb_str, content, flags=re.MULTILINE)
                if n_e8 == 0:
                    content = re.sub(r'(?i)^(nps\s+.*)$', geb_str + r'\n\1', content, flags=re.MULTILINE)
            self.log(f"[*] 已启用 GEB 能量展宽注入 -> 参数: {a}, {b}, {c}")
        else:
            content, n_rm = re.subn(r'(?i)^ft8\s+geb.*\n?', '', content, flags=re.MULTILINE)
            if n_rm > 0: self.log("[*] 未勾选 GEB，已从输入模型中安全剥离遗留的 FT8 展宽卡。")

        self.log(f"[*] --- 物理坐标映射 (包含实体包壳平移) | Z: {z_str} cm | NPS: {raw_nps} ---")

        def save_file(new_content, isotope_name):
            max_n = max([0] + [int(f[:-4]) for f in os.listdir(target_dir) if f.endswith(".txt") and f[:-4].isdigit()])
            fname = f"{max_n + 1}.txt"
            try:
                with open(os.path.join(target_dir, fname), 'w', encoding='utf-8') as f:
                    f.write(new_content)
                    f.write(f"\nc Meta_ID:{isotope_name} | Dist:{distance}cm | Ref:{ref_full_string}\n")
                self.log(f"  [√] 成功封装: {fname} -> {isotope_name}")
            except Exception: pass

        # --- 核心动态源注入口 ---
        content = re.sub(r'(?i)^sdef\s+.*$\n?', '', content, flags=re.MULTILINE)
        content = re.sub(r'(?i)^si\d+\s+.*$\n?', '', content, flags=re.MULTILINE)
        content = re.sub(r'(?i)^sp\d+\s+.*$\n?', '', content, flags=re.MULTILINE)
        content = re.sub(r'(?i)^tr1\s+.*$\n?', '', content, flags=re.MULTILINE)

        base_injection = (
            f"TR1 0 0 {z_str}\n"
            "sdef pos=0 0 -0.005 rad=d1 ext=0 par=2 tr=1 erg={erg}\n"
            "si1 0 0.15\n"
            "sp1 -21 1\n"
            "{spectrum_cards}"
        )

        success = False
        for name, var in self.energy_vars.items():
            if var.get():
                if self.co60_composite_var.get() and "Co-60" in name: continue 
                source_block = base_injection.format(erg=self.energy_dict[name], spectrum_cards="")
                new_content, n = re.subn(r'(?i)^(f8:p,e\s+.*)$', source_block + r'\1', content, flags=re.MULTILINE)
                if n > 0: save_file(new_content, name); success = True

        if self.co60_composite_var.get():
            spec = "si2 L 1.1732 1.3325\nsp2 0.9985 0.9998\n"
            source_block = base_injection.format(erg="d2", spectrum_cards=spec)
            save_file(re.sub(r'(?i)^(f8:p,e\s+.*)$', source_block + r'\1', content, flags=re.MULTILINE), "Co-60_Composite")
            success = True

        if self.na22_composite_var.get():
            spec = "si2 L 0.511 1.274\nsp2 1.798 0.9994\n"
            source_block = base_injection.format(erg="d2", spectrum_cards=spec)
            save_file(re.sub(r'(?i)^(f8:p,e\s+.*)$', source_block + r'\1', content, flags=re.MULTILINE), "Na-22_Composite")
            success = True

        if self.ba133_composite_var.get():
            spec = "si2 L 0.081 0.276 0.303 0.356 0.384\nsp2 0.329 0.071 0.183 0.6205 0.089\n"
            source_block = base_injection.format(erg="d2", spectrum_cards=spec)
            save_file(re.sub(r'(?i)^(f8:p,e\s+.*)$', source_block + r'\1', content, flags=re.MULTILINE), "Ba-133_Composite")
            success = True

        if self.custom_energy_var.get():
            try:
                erg = float(self.custom_energy_val.get())
                source_block = base_injection.format(erg=erg, spectrum_cards="")
                new_content, n = re.subn(r'(?i)^(f8:p,e\s+.*)$', source_block + r'\1', content, flags=re.MULTILINE)
                if n > 0: save_file(new_content, f"def-source({erg*1000:.2f}keV)"); success = True
            except ValueError: pass

        if success: self.log("[*] 输入文件编译完毕。包含PMMA外壳的三维面源物理坐标已精准推演并映射。")

    def sanitize_filename(self, text):
        return re.sub(r'[\\/*?:"<>|]', "", text.replace(" ", "").replace("(", "_").replace(")", ""))

    def silent_remove(self, pattern, directory):
        for f in glob.glob(os.path.join(directory, pattern)):
            try: os.remove(f)
            except OSError: pass

    def start_mpi_execution(self):
        if not self.is_running: self.is_running = True; threading.Thread(target=self._thread_wrapper_mpi, daemon=True).start()

    def start_extract_csv(self):
        if not self.is_running: self.is_running = True; threading.Thread(target=self._thread_wrapper_csv, daemon=True).start()

    def start_origin_automation(self):
        if not self.is_running: self.is_running = True; threading.Thread(target=self._thread_wrapper_origin, daemon=True).start()

    def _thread_wrapper_mpi(self): self._core_mpi_workflow(self._get_target_dir()); self.is_running = False
    def _thread_wrapper_csv(self): self._core_extract_csv(self._get_target_dir()); self.is_running = False
    def _thread_wrapper_origin(self): self._core_origin_automation(self._get_target_dir()); self.is_running = False

    def start_auto_pipeline(self):
        if self.is_running: return messagebox.showwarning("拦截", "系统正在运行中，请等待当前任务结束！")
        target_dir = self._get_target_dir()
        if os.path.exists(target_dir): 
            self.is_running = True
            threading.Thread(target=self._auto_pipeline_thread, args=(target_dir,), daemon=True).start()

    def _auto_pipeline_thread(self, target_dir):
        self.log("\n" + "★"*45 + "\n🚀 [全自动模式启动] 即将按序执行: MPI -> CSV -> Origin\n" + "★"*45)
        if not self._core_mpi_workflow(target_dir): self.log("\n[终止] MPI 计算未发现文件或异常。"); self.is_running = False; return
        if not self._core_extract_csv(target_dir): self.log("\n[终止] 未能提取有效的 CSV 数据。"); self.is_running = False; return
        self._core_origin_automation(target_dir)
        self.log("\n" + "★"*45 + "\n🎉 [完美收官] 全自动流水线已彻底执行完毕！\n" + "★"*45)
        self.is_running = False

    def _core_mpi_workflow(self, target_dir):
        self.log("\n" + "="*40 + "\n[*] 正在启动 MPI 多线程底层接管程序...")
        files_to_run = sorted([f for f in os.listdir(target_dir) if f.endswith(".txt") and f[:-4].isdigit()], key=lambda x: int(x[:-4]))
        if not files_to_run: self.log("[-] 未发现纯数字输入文件。"); return False
            
        mpi_cmd = self.mpi_cmd_var.get()
        success_flag = False
        
        for fname in files_to_run:
            file_path = os.path.join(target_dir, fname)
            meta_id, dist_info, ref_short_name = "Unknown", "Data", "未知"
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
                m_main = re.search(r'Meta_ID:\s*(.*?)\s*\|\s*(?:Distance|Dist):\s*(.*?)(?:\s*\||$)', content, flags=re.IGNORECASE)
                if m_main: meta_id, dist_info = self.sanitize_filename(m_main.group(1)), m_main.group(2).strip()
                m_ref = re.search(r'Ref:\s*(.*?)(?:\s*\||\n|$)', content, flags=re.IGNORECASE)
                if m_ref: ref_short_name = "铝壳表面" if "铝壳" in m_ref.group(1) else "几何中心" if "几何中心" in m_ref.group(1) else "晶体表面" if "晶体" in m_ref.group(1) else self.sanitize_filename(m_ref.group(1))
            except Exception: pass

            base_final = f"{meta_id}-{dist_info}-{ref_short_name}"
            final_out = f"{base_final}.txt"
            counter = 1
            while os.path.exists(os.path.join(target_dir, final_out)): final_out = f"{base_final}_{counter}.txt"; counter += 1
                
            self.log(f"\n[>>>] 提取任务: {fname} -> 物理映射: {final_out}")
            i_txt, o_txt = os.path.join(target_dir, "i.txt"), os.path.join(target_dir, "o.txt")
            if os.path.exists(o_txt): os.remove(o_txt)
            shutil.copyfile(file_path, i_txt)
            
            try:
                subprocess.run(f"{mpi_cmd} i=i.txt o=o.txt", shell=True, cwd=target_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if os.path.exists(o_txt):
                    os.rename(o_txt, os.path.join(target_dir, final_out))
                    self.log(f"    [成功] 数据已重命名为: {final_out}")
                    success_flag = True
                else: self.log(f"    [失败] MCNP 未生成 o.txt！")
            except Exception as e: self.log(f"    [崩溃] {e}")
                
            for p in ["runt*", "mesch*", "comou*", "mdata*", "i.txt", "o.txt"]: self.silent_remove(p, target_dir)

        self.log("\n[完成] MPI 计算结束。")
        return success_flag

    def _core_extract_csv(self, target_dir):
        self.log("\n" + "="*40 + f"\n[*] 正在提取完整 CSV 物理数据: {target_dir}")
        count = 0
        for fname in [f for f in os.listdir(target_dir) if f.endswith(".txt") and not f.replace('.txt', '').isdigit() and f not in ['i.txt', 'o.txt', 'b.txt']]:
            try:
                with open(os.path.join(target_dir, fname), 'r', encoding='utf-8', errors='ignore') as f: lines = f.readlines()
                data_rows, in_tally = [], False
                for line in lines:
                    if re.search(r'^\s+energy\s*$', line, re.IGNORECASE): in_tally = True; continue
                    if in_tally:
                        parts = line.strip().split()
                        if len(parts) == 3:
                            try: data_rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
                            except ValueError: break
                        elif "total" in line.lower(): break
                
                if data_rows:
                    csv_name = os.path.join(target_dir, os.path.splitext(fname)[0] + "_Data.csv")
                    with open(csv_name, 'w', newline='', encoding='utf-8-sig') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow(['Energy (MeV)', 'Tally (Counts/Particle)', 'Relative Error'])
                        writer.writerows(data_rows)
                    self.log(f"    [√ CSV] 成功提取物理数据 -> {os.path.basename(csv_name)}")
                    count += 1
            except Exception: pass
        self.log(f"[完成] 共生成 {count} 个完整 CSV 数据表！")
        return count > 0

    def _core_origin_automation(self, target_dir):
        csv_files = glob.glob(os.path.join(target_dir, "*_Data.csv"))
        if not csv_files: return False

        self.log("\n" + "="*40 + "\n[*] 正在启动 Origin 自动化绘图引擎...")
        try:
            subprocess.run("taskkill /F /IM origin9.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run("taskkill /F /IM origin964.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0)
        except: pass

        temp_workspace = r"C:\MCNP_Tmp"
        if not os.path.exists(temp_workspace): os.makedirs(temp_workspace)
        origin_app = None 
        
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize() 
            origin_app = win32com.client.Dispatch("Origin.ApplicationSI")
            origin_app.Visible = 1
        except Exception as e:
            self.log(f"\n[错误] 连接 Origin 失败: {e}"); return False

        success_count = 0
        for i, csv_path in enumerate(csv_files):
            try:
                real_name = os.path.basename(csv_path).replace(".csv", "")
                final_opj_path = os.path.join(target_dir, f"{real_name}.opj")
                if os.path.exists(final_opj_path):
                    try: os.remove(final_opj_path)
                    except: continue
                
                safe_csv = os.path.join(temp_workspace, f"data_{i}.csv")
                safe_opj = os.path.join(temp_workspace, f"proj_{i}.opj")
                shutil.copyfile(csv_path, safe_csv)
                
                self.log(f"  -> [{i+1}/{len(csv_files)}] 正在绘制: {real_name}")
                origin_app.Execute('document -s; document -n;')
                time.sleep(0.5)
                origin_app.Execute(f'impCSV fname:="{safe_csv.replace(chr(92), "/")}";')
                time.sleep(1.0)  
                origin_app.Execute('wks.col1.type = 4; wks.col2.type = 1; plotxy iy:=2 plot:=200;')
                time.sleep(0.8)  
                origin_app.Execute('layer.x.type = 2; layer.y.type = 2; layer -a;')
                origin_app.Execute(f'page.longname$ = "{real_name}"; page.title = 1;')
                time.sleep(0.5)
                origin_app.Execute(f'save {safe_opj};')
                time.sleep(1.0)
                
                if os.path.exists(safe_opj):
                    shutil.copy2(safe_opj, final_opj_path); success_count += 1
            except Exception as e: self.log(f"  [X] 处理异常: {e}")

        if origin_app:
            try: origin_app.Execute('document -s; document -n;'); time.sleep(0.5); origin_app.Exit()
            except: pass
            
        try: pythoncom.CoUninitialize()
        except: pass

        time.sleep(2.0)
        try: shutil.rmtree(temp_workspace)
        except: pass

        self.log("\n" + "="*40 + f"\n🎉 Origin 作图模块完成！共成功导出 {success_count} 个 .opj 文件。")
        return True

    def _toggle_plot_inputs(self):
        state = 'normal' if self.mode.get() == 2 else 'disabled'
        self.ent_f2.config(state=state)
        self.btn_f2.config(state=state)
        self.btn_merge.config(state=state)

    def _select_file_plot(self, idx):
        path = filedialog.askopenfilename(filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")])
        if path:
            if idx == 1: self.file1_path.set(path)
            else: self.file2_path.set(path)

    def _handle_merge(self):
        if not self.file1_path.get() or not self.file2_path.get():
            messagebox.showwarning("警告", "请先选择两个数据文件！")
            return
        
        save_path = filedialog.asksaveasfilename(defaultextension=".png", initialfile="Comparison_Result.png")
        if save_path:
            try:
                d1 = SpectraEngine.load_data(self.file1_path.get())
                d2 = SpectraEngine.load_data(self.file2_path.get())
                SpectraEngine.generate_plot([d1, d2], save_path)
                messagebox.showinfo("成功", f"图像已保存至:\n{save_path}")
            except Exception as e:
                messagebox.showerror("错误", str(e))

    def _handle_separate(self):
        target_files = [self.file1_path.get()]
        if self.mode.get() == 2:
            target_files.append(self.file2_path.get())
        
        target_files = [f for f in target_files if f]
        if not target_files:
            messagebox.showwarning("警告", "请选择至少一个有效文件！")
            return

        for f in target_files:
            label, x, y = SpectraEngine.load_data(f)
            save_path = filedialog.asksaveasfilename(title=f"保存 {label} 的图", 
                                                   defaultextension=".png", 
                                                   initialfile=f"{label}_Plot.png")
            if save_path:
                SpectraEngine.generate_plot([(label, x, y)], save_path)
        
        messagebox.showinfo("任务完成", "所有选定的图像处理完毕。")

    def geb_log(self, message):
        self.geb_report_box.config(state="normal")
        self.geb_report_box.insert(tk.END, message + "\n")
        self.geb_report_box.see(tk.END)
        self.root.update()

    def parse_peaks_from_filename(self, filename):
        peaks = []
        fn = filename.lower()
        if "composite" in fn:
            if "na-22" in fn or "na22" in fn: peaks = [0.511, 1.274]
            elif "co-60" in fn or "co60" in fn: peaks = [1.173, 1.332]
            elif "ba-133" in fn or "ba133" in fn: peaks = [0.081, 0.276, 0.303, 0.356, 0.384]
        else:
            kev_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*kev', fn)
            if kev_match: peaks.append(float(kev_match.group(1)) / 1000.0)
            else:
                mev_match = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*mev', fn)
                if mev_match: peaks.append(float(mev_match.group(1)))
                else:
                    if "cs-137" in fn or "cs137" in fn: peaks.append(0.662)
                    elif "am-241" in fn or "am241" in fn: peaks.append(0.0595)
        
        if not peaks: return [(0.1, 3.0)]
        
        ranges = []
        for e in peaks:
            window = max(0.05, e * 0.06)
            r_min = round(max(0.01, e - window), 3)
            r_max = round(e + window, 3)
            ranges.append((r_min, r_max))
        return ranges

    def load_geb_reference_file(self):
        filepath = filedialog.askopenfilename(title="选择包含GEB参数的TXT文件", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            match = re.search(r'geb\s+([0-9\.eE\+\-]+)\s+([0-9\.eE\+\-]+)\s+([0-9\.eE\+\-]+)', content, re.IGNORECASE)
            if match:
                self.geb_ref_params = tuple(map(float, match.groups()))
                self.geb_ref_txt_path = filepath
                self.lbl_geb_ref_path.config(text=f"已加载: {os.path.basename(filepath)} | A={self.geb_ref_params[0]}, B={self.geb_ref_params[1]}, C={self.geb_ref_params[2]}", foreground="green")
                self.geb_log(f"[系统] 成功读取基准参数: A={self.geb_ref_params[0]}, B={self.geb_ref_params[1]}, C={self.geb_ref_params[2]}")
            else:
                messagebox.showerror("解析失败", "未找到有效的 'geb A B C' 参数格式。")
        except Exception as e:
            messagebox.showerror("读取错误", f"无法读取文件:\n{e}")

    def add_geb_csv_files(self):
        filepaths = filedialog.askopenfilenames(title="选择能谱CSV文件 (可多选)", filetypes=[("CSV Files", "*.csv")])
        for path in filepaths:
            if any(item['path'] == path for item in self.geb_csv_files): continue
            ranges = self.parse_peaks_from_filename(os.path.basename(path))
            self.geb_csv_files.append({'path': path, 'peaks': ranges})
            range_str = ", ".join([f"峰{i+1}: {r[0]}-{r[1]}" for i, r in enumerate(ranges)])
            self.geb_tree.insert("", tk.END, values=(os.path.basename(path), path, range_str))
        self.geb_log(f"[系统] 成功引入 {len(filepaths)} 个文件。系统已根据文件名元数据，自动挂载拆分出所需的特征峰区间。")

    def remove_geb_selected_csv(self):
        selected_items = self.geb_tree.selection()
        if not selected_items: return
        for item in selected_items:
            path_to_remove = self.geb_tree.item(item, 'values')[1]
            self.geb_csv_files = [f for f in self.geb_csv_files if f['path'] != path_to_remove]
            self.geb_tree.delete(item)

    def on_geb_tree_double_click(self, event):
        item = self.geb_tree.selection()
        if not item: return
        item = item[0]
        values = self.geb_tree.item(item, 'values')
        target_path = values[1]
        
        target_dict = next((f for f in self.geb_csv_files if f['path'] == target_path), None)
        if not target_dict: return
        
        edit_win = tk.Toplevel(self.root)
        edit_win.title("修改多重寻峰区间 (ROI)")
        edit_win.geometry("420x350")
        edit_win.grab_set()
        
        canvas = tk.Canvas(edit_win)
        scrollbar = ttk.Scrollbar(edit_win, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        ttk.Label(scrollable_frame, text=f"正在调整文件: {values[0]}", font=self.font_bold, foreground="#0078D7").pack(pady=10)
        
        entry_refs = []
        for i, (e_min, e_max) in enumerate(target_dict['peaks']):
            f_peak = ttk.LabelFrame(scrollable_frame, text=f"峰 {i+1} 范围 (MeV)")
            f_peak.pack(fill=tk.X, padx=15, pady=5)
            
            ttk.Label(f_peak, text="下限:").grid(row=0, column=0, padx=5, pady=5)
            ent_min = ttk.Entry(f_peak, width=10); ent_min.insert(0, str(e_min))
            ent_min.grid(row=0, column=1)
            
            ttk.Label(f_peak, text="上限:").grid(row=0, column=2, padx=5, pady=5)
            ent_max = ttk.Entry(f_peak, width=10); ent_max.insert(0, str(e_max))
            ent_max.grid(row=0, column=3)
            
            entry_refs.append((ent_min, ent_max))
        
        def save_edit():
            try:
                new_ranges = []
                for ent_min, ent_max in entry_refs:
                    n_min, n_max = float(ent_min.get()), float(ent_max.get())
                    if n_min >= n_max: raise ValueError("存在下限大于等于上限的非法输入")
                    new_ranges.append((n_min, n_max))
                
                target_dict['peaks'] = new_ranges
                range_str = ", ".join([f"峰{i+1}: {r[0]}-{r[1]}" for i, r in enumerate(new_ranges)])
                self.geb_tree.item(item, values=(values[0], target_path, range_str))
                edit_win.destroy()
            except ValueError as e:
                messagebox.showerror("错误", f"输入格式有误: {e}")
                
        ttk.Button(scrollable_frame, text="✅ 保存所有区间修改", command=save_edit).pack(pady=15)

    @staticmethod
    def geb_formula(E, a, b, c):
        return a + b * np.sqrt(np.maximum(E + c * E**2, 0))

    def extract_geb_features(self, file_path, e_min, e_max):
        try:
            df = pd.read_csv(file_path)
            x_cols = [c for c in df.columns if 'energy' in c.lower() or 'mev' in c.lower()]
            y_cols = [c for c in df.columns if 'tally' in c.lower() or 'count' in c.lower()]
            E = df[x_cols[0]].values if x_cols else df.iloc[:, 0].values
            counts = df[y_cols[0]].values if y_cols else df.iloc[:, 1].values
            
            mask = (E > e_min) & (E < e_max)
            E_roi, C_roi = E[mask], counts[mask]
            
            if len(E_roi) == 0: return None, None, None
                
            peak_idx = np.argmax(C_roi)
            peak_E = E_roi[peak_idx]
            half_max = C_roi[peak_idx] / 2.0
            
            left_E, right_E = None, None
            for i in range(peak_idx, 0, -1):
                if C_roi[i-1] <= half_max <= C_roi[i]:
                    left_E = E_roi[i-1] + (half_max - C_roi[i-1]) * (E_roi[i] - E_roi[i-1]) / (C_roi[i] - C_roi[i-1])
                    break
            for i in range(peak_idx, len(C_roi)-1):
                if C_roi[i+1] <= half_max <= C_roi[i]:
                    right_E = E_roi[i] + (half_max - C_roi[i]) * (E_roi[i+1] - E_roi[i]) / (C_roi[i+1] - C_roi[i])
                    break
                    
            fwhm = (right_E - left_E) if (left_E and right_E) else None
            df_ret = pd.DataFrame({'E': E, 'counts': counts})
            return peak_E, fwhm, df_ret
        except Exception as e:
            self.geb_log(f"⚠️ 解析错误: {e}")
            return None, None, None

    def calculate_net_efficiency(self, df, peak_E, fwhm, sampling_fraction=1.0):
        try:
            E = df['E'].values
            counts = df['counts'].values

            roi_min = peak_E - 1.5 * fwhm
            roi_max = peak_E + 1.5 * fwhm
            mask = (E >= roi_min) & (E <= roi_max)
            roi_counts = counts[mask]

            if len(roi_counts) < 6: return 0, 0, 0

            gross_area = np.sum(roi_counts)
            left_baseline = np.mean(roi_counts[:3])
            right_baseline = np.mean(roi_counts[-3:])
            num_bins = len(roi_counts)

            background_area = (left_baseline + right_baseline) * num_bins / 2.0
            net_raw = gross_area - background_area
            net_efficiency = net_raw / sampling_fraction if sampling_fraction > 1e-9 else net_raw

            return gross_area, background_area, net_efficiency
        except Exception:
            return 0, 0, 0

    def run_geb_analysis(self):
        if not self.geb_ref_params or not self.geb_csv_files:
            messagebox.showwarning("条件缺失", "请确保已加载基准TXT和至少一个智能CSV文件。")
            return
            
        total_peaks_defined = sum(len(f['peaks']) for f in self.geb_csv_files)
        if total_peaks_defined < 3:
            if not messagebox.askyesno("精度警告", f"当前全系统仅提取出 {total_peaks_defined} 个特征峰。\n反推 A,B,C 必须至少 3 个点。强行拟合可能导致错误。\n是否继续？"):
                return

        self.geb_log("\n" + "█"*65)
        self.geb_log("🚀 启动高通量特征解析: 多文件/多峰并发 -> 康普顿/效率运算 -> 深度反推")
        self.geb_log("█"*65)
        
        self.geb_data_points = []
        
        for f_info in self.geb_csv_files:
            file_name = os.path.basename(f_info['path'])
            self.geb_log(f"\n✅ 进入作业文件: {file_name}")

            # 从文件名识别核素，用于采样分数归一化
            fn_upper = file_name.upper()
            detected_nuc = None
            for key in self.sp2_weights:
                parts = key.split('-')
                if parts[0] in fn_upper and parts[1] in fn_upper:
                    detected_nuc = key
                    break

            for i, (e_min, e_max) in enumerate(f_info['peaks']):
                p_E, p_FWHM, df = self.extract_geb_features(f_info['path'], e_min, e_max)
                if p_E is not None and p_FWHM is not None:
                    self.geb_data_points.append((p_E, p_FWHM))

                    # 采样分数归一化：仅对复合源文件生效（与 compare.py 逻辑一致）
                    is_composite = 'composite' in file_name.lower()
                    sp2_dict = self.sp2_weights.get(detected_nuc, {}) if (detected_nuc and is_composite) else {}
                    if sp2_dict:
                        closest_e = min(sp2_dict.keys(), key=lambda k: abs(k - p_E))
                        sp2_weight = sp2_dict.get(closest_e, 1.0)
                        sp2_total = sum(sp2_dict.values())
                        sampling_fraction = sp2_weight / sp2_total if sp2_total > 1e-9 else 1.0
                    else:
                        sampling_fraction = 1.0

                    compton_edge = (2 * p_E**2) / (self.M_E_C2 + 2 * p_E)
                    g_area, b_area, net_eff = self.calculate_net_efficiency(df, p_E, p_FWHM, sampling_fraction)

                    self.geb_log(f"   [通道 {i+1}] 搜索域: {e_min} ~ {e_max} MeV")
                    self.geb_log(f"   ► 实测峰位能量: {p_E:.5f} MeV  |  精确半高宽(FWHM): {p_FWHM:.5f} MeV")
                    self.geb_log(f"   ► 理论康普顿边缘: {compton_edge:.5f} MeV | 康普顿坪: 0.0000 - {compton_edge:.5f} MeV")
                    self.geb_log(f"   ► 效率积分规则(±1.5FWHM): 扣除梯形本底 {b_area:.6e} | 净效率(已归一化) {net_eff:.6e}")
                    self.geb_log("   " + "-" * 60)
                else:
                    self.geb_log(f"   ❌ [通道 {i+1}] 搜索失败: 在 {e_min} ~ {e_max} MeV 区域内数据异常或未寻获全能峰。")
        
        if len(self.geb_data_points) < 1:
            self.geb_log("❌ 严重错误：全盘搜索未收集到任何有效数据点。")
            return

        E_arr = np.array([pt[0] for pt in self.geb_data_points])
        F_arr = np.array([pt[1] for pt in self.geb_data_points])
        
        try:
            popt, _ = curve_fit(self.geb_formula, E_arr, F_arr, 
                                p0=[-0.01, 0.05, 0.2], 
                                bounds=([-1.0, 0.0, 0.0], [1.0, 5.0, 5.0]),
                                maxfev=10000)
            self.generate_geb_report(popt, E_arr, F_arr)
        except Exception as e:
            self.geb_log(f"\n❌ 灾难性错误: 非线性曲面拟合引擎崩溃 -> {e}")

    def generate_geb_report(self, fitted_params, E_arr, F_arr):
        self.geb_log("\n" + "━"*25 + " 📊 探测器晶体响应 GEB 最终反推报告 " + "━"*25)
        self.geb_log(f"{'参数':<8} | {'基准参考值 (25.txt)':<20} | {'当前物理数据倒推值':<20} | {'绝对误差'}")
        self.geb_log("-" * 80)
        
        labels = ['A', 'B', 'C']
        for i in range(3):
            ref_val = self.geb_ref_params[i]
            fit_val = fitted_params[i]
            diff = fit_val - ref_val
            self.geb_log(f"{labels[i]:<8} | {ref_val:<25.6f} | {fit_val:<22.6f} | {diff:+.6f}")
            
        self.geb_log("\n[反推模型微观交叉验证明细]")
        self.geb_log(f"{'实测峰位(MeV)':<15} | {'实际物理谱FWHM':<15} | {'推断模型预期FWHM':<18} | {'拟合偏差'}")
        self.geb_log("-" * 80)
        
        for e, f_actual in zip(E_arr, F_arr):
            f_calc = self.geb_formula(e, *fitted_params)
            error_pct = abs(f_calc - f_actual) / f_actual * 100
            self.geb_log(f"{e:<20.4f} | {f_actual:<18.5f} | {f_calc:<22.5f} | {error_pct:.2f}%")
        self.geb_log("━" * 80)

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    root = tk.Tk()
    app = MCNPPlatformApp(root)
    root.mainloop()