#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
键盘模块：生成各种 InlineKeyboardMarkup。
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from permissions import is_admin


def main_menu(user_id: int) -> InlineKeyboardMarkup:
    """生成主菜单键盘。

    Args:
        user_id: 当前用户 ID，用于判断是否显示管理员按钮。

    Returns:
        InlineKeyboardMarkup 对象。
    """
    rows = [
        [
            InlineKeyboardButton(
                "➡️ 转发备份",
                callback_data="forward_guide",
            )
        ],
        [
            InlineKeyboardButton(
                "🔍 查询 ID",
                callback_data="searchid_guide",
            )
        ],
        [
            InlineKeyboardButton(
                "📖 使用说明",
                callback_data="help",
            )
        ]
    ]

    if is_admin(user_id):
        rows.append(
            [
                InlineKeyboardButton(
                    "⚙️ 绑定管理",
                    callback_data="binding_menu",
                )
            ]
        )

    return InlineKeyboardMarkup(rows)


def binding_menu() -> InlineKeyboardMarkup:
    """生成绑定管理菜单键盘。

    Returns:
        InlineKeyboardMarkup 对象。
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ 添加 / 修改绑定",
                    callback_data="binding_add",
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑 删除绑定",
                    callback_data="binding_delete",
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 查看全部绑定",
                    callback_data="binding_list",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔍 检查群组",
                    callback_data="binding_check",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ 返回",
                    callback_data="main_menu",
                )
            ],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    """生成取消操作键盘。

    Returns:
        InlineKeyboardMarkup 对象。
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ 取消",
                    callback_data="binding_cancel",
                )
            ]
        ]
    )


def confirm_binding_keyboard() -> InlineKeyboardMarkup:
    """生成确认绑定键盘。

    Returns:
        InlineKeyboardMarkup 对象。
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ 确认绑定",
                    callback_data="binding_confirm",
                ),
                InlineKeyboardButton(
                    "❌ 取消",
                    callback_data="binding_cancel",
                ),
            ]
        ]
    )