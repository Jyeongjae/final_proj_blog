from django.shortcuts import render, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404
from .models import Post, Tag, Comment, News
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from .forms import CommentForm
from django.utils import timezone
from django.utils.text import slugify

from django.conf import settings
from django.http import JsonResponse
from .dalle import save_gen_img, OpenAI, BadRequestError
import json
import os
from dotenv import load_dotenv
from django.core.files import File
from urllib.request import urlopen
from tempfile import NamedTemporaryFile

load_dotenv()

class PostList(ListView):
    model = Post
    ordering = '-pk'
    paginate_by = 5

    def get_context_data(self, **kwargs):
        context = super(PostList, self).get_context_data(**kwargs)
        # 오늘 날짜의 뉴스 필터링
        today = timezone.now().date()
        today_news = News.objects.filter(created_at__date=today)

        # 템플릿에 전달
        context['today_news'] = today_news
        context['comment_form'] = CommentForm
        return context

class PostDetail(DetailView):
    model = Post

    def get_context_data(self, **kwargs):
        context = super(PostDetail, self).get_context_data()
        # 오늘 날짜의 뉴스 필터링
        today = timezone.now().date()
        today_news = News.objects.filter(created_at__date=today)

        # 템플릿에 전달
        context['today_news'] = today_news
        context['comment_form'] = CommentForm
        return context

class PostUpdate(LoginRequiredMixin, UpdateView):
    model = Post
    fields = ['title', 'content', 'head_image']

    template_name = 'blog/post_update_form.html'

    def get_context_data(self, **kwargs):
        context = super(PostUpdate, self).get_context_data()
        if self.object.tags.exists():
            tags_str_list = list()
            for t in self.object.tags.all():
                tags_str_list.append(t.name)
            context['tags_str_default'] = '; '.join(tags_str_list)
        return context

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user == self.get_object().author:
            return super(PostUpdate, self).dispatch(request, *args, **kwargs)
        else:
            raise PermissionDenied

    def form_valid(self, form):
        response = super(PostUpdate, self).form_valid(form)
        self.object.tags.clear()
        tags_str = self.request.POST.get('tags_str')
        if tags_str:
            tags_str = tags_str.strip()
            tags_str = tags_str.replace(',', ';')
            tags_list = tags_str.split(';')
            for t in tags_list:
                t = t.strip()
                tag, is_tag_created = Tag.objects.get_or_create(name=t)
                if is_tag_created:
                    tag.slug = slugify(t, allow_unicode=True)
                    tag.save()
                self.object.tags.add(tag)
        return response

def new_comment(request, pk):
    if request.user.is_authenticated:
        post = get_object_or_404(Post, pk=pk)
        if request.method == 'POST':
            comment_form = CommentForm(request.POST)

            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.post = post
                comment.author = request.user
                comment.save()
                return redirect(comment.get_absolute_url())
        else:
            return redirect(post.get_absolute_url())
    else:
        raise PermissionDenied

class CommentUpdate(LoginRequiredMixin, UpdateView):
    model = Comment
    form_class = CommentForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user == self.get_object().author:
            return super(CommentUpdate, self).dispatch(request, *args, **kwargs)
        else:
            raise PermissionDenied

def delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    post = comment.post
    if request.user.is_authenticated and request.user == comment.author:
        comment.delete()
        return redirect(post.get_absolute_url())
    else:
        raise PermissionDenied

class PostSearch(PostList):
    paginate_by = None
    def get_queryset(self):
        q = self.kwargs['q']
        post_list = Post.objects.filter(
            Q(title__contains=q)
        ).distinct()
        return post_list
    def get_context_data(self, **kwargs):
        context = super(PostSearch, self).get_context_data()
        q = self.kwargs['q']
        context['search_info'] = f'Search: {q}'
        return context

def generate_unique_slug(name):
    slug = slugify(name, allow_unicode=True)
    unique_slug = slug
    number = 1
    while Tag.objects.filter(slug=unique_slug).exists():
        unique_slug = f"{slug}-{number}"
        number += 1
    return unique_slug


class PostCreate(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Post
    fields = ['title', 'content', 'head_image']
    template_name = 'blog/create_new_post.html'

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_staff

    def form_valid(self, form):
        current_user = self.request.user
        if current_user.is_authenticated and (current_user.is_staff or current_user.is_superuser):
            form.instance.author = current_user

            # hidden input에서 이미지 URL 가져오기
            generated_image_url = self.request.POST.get('generated_image_url')
            if generated_image_url:
                # URL에서 이미지를 열어 임시 파일로 저장한 후 head_image에 첨부
                img_temp = NamedTemporaryFile(delete=True)
                img_temp.write(urlopen(generated_image_url).read())
                img_temp.flush()

                # 파일 이름을 지정하여 저장 (경로를 제거하고 파일명만 사용)
                file_name = os.path.basename(generated_image_url)
                form.instance.head_image.save(file_name, File(img_temp), save=False)

            response = super(PostCreate, self).form_valid(form)

            # 태그 추가
            tags_str = self.request.POST.get('tags_str')
            if tags_str:
                tags_str = tags_str.strip().replace(',', ';')
                tags_list = tags_str.split(';')
                for t in tags_list:
                    t = t.strip()
                    existing_tag = Tag.objects.filter(name=t).first()
                    if existing_tag:
                        tag = existing_tag
                    else:
                        tag = Tag(name=t)
                        tag.slug = generate_unique_slug(t)  # 고유 슬러그 생성 함수 사용
                        tag.save()
                    self.object.tags.add(tag)

            return response
        else:
            return redirect('/blog/')

def generate_image(request):
    if request.method == "POST":
        data = json.loads(request.body)
        txt_response = data.get("txt_response", "")
        client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

        try:
            filename = save_gen_img(client, txt_response)
            file_url = request.build_absolute_uri(os.path.join(settings.MEDIA_URL, 'generated_images', filename))
        except BadRequestError:
            filename = save_gen_img(client, "시장 경제 활동")
            file_url = request.build_absolute_uri(os.path.join(settings.MEDIA_URL, 'generated_images', filename))

        return JsonResponse({"filename": filename, "file_url": file_url})
