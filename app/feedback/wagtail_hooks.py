from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from wagtail import hooks
from wagtail.admin.panels import FieldPanel, FieldRowPanel
from wagtail.admin.site_summary import SummaryItem
from wagtail.admin.ui.tables import BooleanColumn, Column, DateColumn
from wagtail.snippets.bulk_actions.snippet_bulk_action import SnippetBulkAction
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from feedback.models import Comment


class CommentViewSet(SnippetViewSet):
    """The moderation queue: every visitor comment, approved or waiting."""

    model = Comment
    icon = "comment"
    menu_label = _("Comments")
    menu_name = "comments"
    menu_order = 900
    add_to_admin_menu = True
    add_to_reference_index = False
    list_display = [
        "__str__",
        BooleanColumn("is_approved", label=_("Approved")),
        Column("entry_title", label=_("Post")),
        Column("display_name", label=_("Author")),
        DateColumn("created_at", label=_("Posted")),
    ]
    list_filter = ["is_approved", "created_at"]
    search_fields = ["body", "author_name", "author_email"]
    ordering = ["-created_at"]
    list_per_page = 50
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_fields = [
        "entry_page_id", "author_name", "author_email", "body",
        "is_approved", "created_at", "moderated_at", "moderated_by",
        "session_key", "ip_address",
    ]
    admin_url_namespace = "comment_views"
    base_url_path = "internal/comments"

    panels = [
        FieldPanel("is_approved"),
        FieldPanel("body"),
        FieldRowPanel([
            FieldPanel("author_name"),
            FieldPanel("author_email"),
        ]),
    ]


register_snippet(CommentViewSet)


class ApprovalBulkAction(SnippetBulkAction):
    models = [Comment]
    template_name = "feedback/bulk_actions/confirm_bulk_approval.html"
    approve = True

    def check_perm(self, obj):
        return self.request.user.has_perm('feedback.change_comment')

    def get_execution_context(self):
        return {**super().get_execution_context(), 'user': self.request.user}

    @classmethod
    def execute_action(cls, objects, user=None, **kwargs):
        for comment in objects:
            if cls.approve:
                comment.approve(user)
            else:
                comment.unapprove(user)
        return len(objects), 0

    def get_context_data(self, **kwargs):
        return super().get_context_data(approve=self.approve, **kwargs)


@hooks.register('register_bulk_action')
class ApproveBulkAction(ApprovalBulkAction):
    display_name = _("Approve")
    action_type = "approve"
    aria_label = _("Approve selected comments")
    action_priority = 10
    approve = True

    def get_success_message(self, num_parent_objects, num_child_objects):
        return ngettext(
            "%(count)d comment approved.",
            "%(count)d comments approved.",
            num_parent_objects,
        ) % {'count': num_parent_objects}


@hooks.register('register_bulk_action')
class UnapproveBulkAction(ApprovalBulkAction):
    display_name = _("Unapprove")
    action_type = "unapprove"
    aria_label = _("Unapprove selected comments")
    action_priority = 11
    approve = False

    def get_success_message(self, num_parent_objects, num_child_objects):
        return ngettext(
            "%(count)d comment hidden pending approval.",
            "%(count)d comments hidden pending approval.",
            num_parent_objects,
        ) % {'count': num_parent_objects}


class PendingCommentsSummaryItem(SummaryItem):
    order = 400
    template_name = "feedback/home/site_summary_comments.html"

    def is_shown(self):
        return self.request.user.has_perm('feedback.change_comment')

    def get_context_data(self, parent_context):
        return {'pending_count': Comment.objects.pending().count()}


@hooks.register('construct_homepage_summary_items')
def add_pending_comments_summary_item(request, items):
    items.append(PendingCommentsSummaryItem(request))
