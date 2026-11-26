#!/usr/bin/env ruby
# encoding: UTF-8
require 'cgi'
require 'base64'
require 'fileutils'
require 'json'
require 'open3'
require 'thread'
require 'tmpdir'
require 'uri'

IMAGE_MIME_TYPES = {
  '.jpg' => 'image/jpeg',
  '.png' => 'image/png',
  '.webp' => 'image/webp',
  '.gif' => 'image/gif',
  '.svg' => 'image/svg+xml'
}.freeze
DETAIL_MEDIA_TYPES = %w[image gif video].freeze

def fail_with(message)
  abort("product-page-capture: #{message}")
end

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'.freeze

def is_local_media?(value)
  str = value.to_s.strip
  return true if str.start_with?('file://')
  return true if File.exist?(str)
  false
end

def resolve_local_path(value)
  str = value.to_s.strip
  if str.start_with?('file://')
    path = URI.parse(str).path
    CGI.unescape(path)
  else
    File.expand_path(str)
  end
rescue => _e
  File.expand_path(value.to_s.sub(/^file:\/\//, ''))
end

def valid_media_url(value)
  return value if is_local_media?(value)
  uri = URI.parse(value.to_s)
  fail_with("不是有效的 HTTP(S) 或本地媒体地址：#{value}") unless %w[http https].include?(uri.scheme) && uri.host
  value
rescue URI::InvalidURIError
  fail_with("无效媒体地址：#{value}")
end

def remote_url(value)
  valid_media_url(value)
end

def system_proxy
  @system_proxy ||= begin
    env_p = ENV['https_proxy'] || ENV['all_proxy'] || ENV['http_proxy']
    if env_p && !env_p.empty?
      env_p
    else
      out, _err, st = Open3.capture3('scutil', '--proxy')
      if st.success?
        http_on = out =~ /HTTPEnable\s*:\s*1/
        https_on = out =~ /HTTPSEnable\s*:\s*1/
        host = out[/HTTPProxy\s*:\s*(\S+)/, 1]
        port = out[/HTTPPort\s*:\s*(\d+)/, 1]
        if (http_on || https_on) && host && port
          "http://#{host}:#{port}"
        end
      end
    end
  rescue
    nil
  end
end

def extension_for(path)
  head = File.binread(path, 32)
  return '.gif' if head.start_with?('GIF87a', 'GIF89a')
  return '.webp' if head[0, 4] == 'RIFF' && head[8, 4] == 'WEBP'
  return '.jpg' if head.start_with?("\xFF\xD8\xFF".b)
  return '.png' if head.start_with?("\x89PNG\r\n\x1A\n".b)
  return '.mp4' if head[4, 4] == 'ftyp'
  return '.webm' if head.start_with?("\x1A\x45\xDF\xA3".b)
  return '.svg' if head.lstrip.start_with?('<svg', '<?xml')
  fail_with("无法识别下载文件的格式：#{path}")
end

def download(url, folder, index)
  if is_local_media?(url)
    src = resolve_local_path(url)
    fail_with("本地媒体文件不存在或为空：#{src}") unless File.exist?(src) && File.size?(src)
    final = File.join(folder, format('%02d%s', index, extension_for(src)))
    FileUtils.cp(src, final)
    return final
  end

  valid_media_url(url)
  temp = File.join(folder, format('%02d.download', index))
  accept = if url.match?(/\.webp(?:\?|$)/i)
    'Accept: image/webp'
  elsif url.match?(/\.gif(?:\?|$)/i)
    'Accept: image/gif'
  elsif url.match?(/\.jpe?g(?:\?|$)/i)
    'Accept: image/jpeg'
  else
    'Accept: */*'
  end

  base_cmd = [
    'curl', '--location', '--fail', '--silent', '--show-error',
    '--retry', '2', '--connect-timeout', '15', '--max-time', '60',
    '-H', accept,
    '-A', USER_AGENT
  ]

  _out, err, status = Open3.capture3(*(base_cmd + [url, '-o', temp]))

  # 如果直接下载失败且存在系统代理，自动追加代理重试一次
  if (!status.success? || !File.size?(temp)) && system_proxy && !url.match?(%r{https?://(127\.0\.0\.1|localhost)})
    _out, err, status = Open3.capture3(*(base_cmd + ['--proxy', system_proxy, '--noproxy', '', url, '-o', temp]))
  end

  unless status.success? && File.size?(temp)
    fail_with("下载失败：#{url}\n#{err}\n提示：若遇到防爬或超时，可先通过浏览器截图/保存到本地，并在清单中使用本地文件路径（如 file:///... 或相对路径）。")
  end

  final = File.join(folder, format('%02d%s', index, extension_for(temp)))
  FileUtils.mv(temp, final)
  final
end

def download_concurrently(items, concurrency: 8)
  return if items.empty?
  queue = Queue.new
  items.each { |item| queue << item }
  errors = Queue.new

  worker_count = [concurrency, items.size].min
  threads = Array.new(worker_count) do
    Thread.new do
      while errors.empty?
        item = begin
          queue.pop(true)
        rescue ThreadError
          nil
        end
        break unless item
        url, folder, index = item
        begin
          download(url, folder, index)
        rescue => e
          errors << e.message
        rescue SystemExit => e
          errors << e.message
        end
      end
    end
  end
  threads.each(&:join)
  fail_with(errors.pop) unless errors.empty?
end

def feature_code(template, tags)
  return '' if tags.nil? || tags.empty?
  pattern = /<span class="product-feature-tag">(\s*)标签\d+(\s*)<\/span>/
  placeholders = template.scan(pattern).length
  fail_with('span 模板缺少标签占位符') if placeholders.zero?
  position = 0
  code = template.gsub(pattern) do
    match = Regexp.last_match
    if position < tags.length
      value = CGI.escapeHTML(tags[position])
      position += 1
      %(<span class="product-feature-tag">#{match[1]}#{value}#{match[2]}</span>)
    else
      ''
    end
  end
  if position < tags.length
    additional = tags[position..].map do |tag|
      %(<span class="product-feature-tag"> #{CGI.escapeHTML(tag)} </span>)
    end.join(' ')
    fail_with('span 模板缺少 </div>') unless code.include?('</div>')
    code = code.sub('</div>', " #{additional} </div>")
  end
  fail_with('生成的 span 数量不等于标签数量') unless code.scan('<span class="product-feature-tag">').length == tags.length
  code.strip
end

def detail_markup(block, media_path = nil)
  type = block.fetch('type')
  case type
  when 'image', 'gif'
    mime_type = IMAGE_MIME_TYPES[File.extname(media_path)]
    fail_with("无法嵌入详情图片：#{media_path}") unless mime_type
    encoded = Base64.strict_encode64(File.binread(media_path))
    %(<img src="data:#{mime_type};base64,#{encoded}" alt="" loading="eager">)
  when 'video'
    url = CGI.escapeHTML(remote_url(block.fetch('url')))
    %(<video src="#{url}" controls playsinline></video>)
  when 'text'
    text_val = block['text'] || block['content'] || ''
    content = CGI.escapeHTML(text_val.to_s).gsub("\n", '<br>')
    "<p>#{content}</p>"
  when 'heading'
    level = [[block.fetch('level', 2).to_i, 1].max, 6].min
    text_val = block['text'] || block['content'] || ''
    "<h#{level}>#{CGI.escapeHTML(text_val.to_s)}</h#{level}>"
  when 'list'
    tag = block['ordered'] ? 'ol' : 'ul'
    items = block.fetch('items').map { |item| "<li>#{CGI.escapeHTML(item.to_s)}</li>" }.join
    "<#{tag}>#{items}</#{tag}>"
  else
    fail_with("不支持的详情块类型：#{type}")
  end
end

usage = '用法：ruby save_product_page.rb <采集清单.json> <输出根目录>（商品目录名由清单的 folder_name 决定）'
if [['-h'], ['--help']].include?(ARGV)
  puts usage
  exit
end
fail_with(usage) unless ARGV.length == 2
manifest_path, output_root = ARGV
data = JSON.parse(File.read(manifest_path, encoding: 'UTF-8'))
title = data.fetch('title').to_s.strip
intro = data.fetch('intro')
tags = data.fetch('tags')
quantity_discounts = data.fetch('quantity_discounts', [])
gallery = data.fetch('gallery')
details = data.fetch('details')
fail_with('商品名、轮播图和详情块都必须存在') if title.empty? || gallery.empty? || details.empty?
fail_with('简介格式必须是数组') unless intro.nil? || intro.is_a?(Array)
fail_with('标签格式必须是数组') unless tags.nil? || tags.is_a?(Array)
intro ||= []
tags ||= []
fail_with('轮播图格式必须是数组') unless gallery.is_a?(Array)
fail_with('详情块格式必须是数组') unless details.is_a?(Array)

safe_name = (data['folder_name'] || data['folder'] || title).gsub(/[\/:\x00-\x1F]/, '-').strip
fail_with('商品名超过文件夹长度限制') if safe_name.bytesize > 240
FileUtils.mkdir_p(output_root)
destination = File.join(output_root, safe_name)
fail_with("目标文件夹已存在，请先检查：#{destination}") if File.exist?(destination)
template_path = File.expand_path('../assets/product-feature-tags.html', __dir__)
template = File.read(template_path, encoding: 'UTF-8')

Dir.mktmpdir('product-page-capture-', output_root) do |staging|
  folder = File.join(staging, safe_name)
  gallery_dir = File.join(folder, '轮播图')
  detail_dir = File.join(folder, '详情图')
  FileUtils.mkdir_p([gallery_dir, detail_dir])

  gallery_items = gallery.each_with_index.map do |media, index|
    url = media.is_a?(Hash) ? media.fetch('url') : media
    [url, gallery_dir, index + 1]
  end

  detail_items = []
  image_index = 0
  details.each do |block|
    next unless DETAIL_MEDIA_TYPES.include?(block.fetch('type'))
    image_index += 1
    detail_items << [block.fetch('url'), detail_dir, image_index]
  end

  download_concurrently(gallery_items)
  images = Dir.children(gallery_dir).select do |filename|
    IMAGE_MIME_TYPES.key?(File.extname(filename))
  end
  cover = images.min_by(&:to_i)
  if cover
    FileUtils.cp(File.join(gallery_dir, cover), File.join(folder, "封面#{File.extname(cover)}"))
  end
  download_concurrently(detail_items)

  basic = ["# #{title}", '']
  intro.each do |entry|
    heading = entry.fetch('heading').to_s
    body = entry.fetch('body').to_s
    basic << heading << ''
    basic << body << '' unless body.empty?
  end
  basic << tags.join(' · ') << '' unless tags.empty?
  unless quantity_discounts.empty?
    basic << '## 多件折扣' << ''
    quantity_discounts.each do |entry|
      line = "- Buy #{entry.fetch('quantity')}"
      discount = entry['discount']
      line += " - Save #{discount}" if discount
      basic << line
    end
    basic << ''
  end
  fc = feature_code(template, tags)
  basic << fc << '' unless fc.empty?
  File.write(File.join(folder, '商品名称_简介_标签.md'), basic.join("\n").strip + "\n")

  detail_files = Dir.children(detail_dir).sort_by(&:to_i).each
  html_header = <<~HTML
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>商品详情</title>
      <style>
        html, body { margin: 0; padding: 0; background: #fff; }
        main { width: min(100%, 750px); margin: 0 auto; }
        img, video { display: block; width: 100%; height: auto; margin: 0; padding: 0; border: 0; }
      </style>
    </head>
    <body>
      <main>
  HTML
  File.open(File.join(folder, '商品详情_打开后全选复制.html'), 'w:UTF-8') do |html|
    html.write(html_header)
    details.each do |block|
      media_path = if DETAIL_MEDIA_TYPES.include?(block.fetch('type'))
        File.join(detail_dir, detail_files.next)
      end
      html.puts(detail_markup(block, media_path))
    end
    html.write("  </main>\n</body>\n</html>\n")
  end
  FileUtils.mv(folder, destination)
end
puts "保存完成：#{destination}；轮播 #{gallery.length} 项，详情 #{details.length} 块"
