#!/usr/bin/env python3
"""
Generic adapter for service manifest generation.

Fallback heuristic-based extraction for services that don't match
other specific adapters.
"""

import re
import os
from typing import Dict, List, Any, Optional
from .base_adapter import BaseAdapter, AdapterResult


class GenericAdapter(BaseAdapter):
    """Generic adapter for unknown service formats."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the generic adapter."""
        super().__init__(config)
        self.supported_extensions = ['.py', '.js', '.ts', '.go', '.rs', '.java', '.cs', '.php', '.rb']
        self.supported_files = []
    
    def can_process(self, file_path: str, content: str) -> bool:
        """Check if this adapter can process the file."""
        # This is a fallback adapter - it can process any file
        # but with low confidence
        return True
    
    def extract_manifest(self, file_path: str, content: str, 
                        repo_metadata: Optional[Dict[str, Any]] = None) -> AdapterResult:
        """Extract service manifest using generic heuristics."""
        try:
            # Extract basic information using heuristics
            manifest = self._extract_service_manifest(
                file_path, content, repo_metadata
            )
            
            # Validate manifest
            errors = self.validate_manifest(manifest)
            if errors:
                return AdapterResult(
                    success=False,
                    errors=errors,
                    service_manifest=manifest
                )
            
            return AdapterResult(
                success=True,
                service_manifest=manifest,
                confidence=0.3,  # Low confidence for generic extraction
                metadata={
                    'extracted_from': 'generic',
                    'file_path': file_path,
                    'file_size': len(content),
                    'heuristics_used': self._get_heuristics_used(file_path, content)
                }
            )
            
        except Exception as e:
            return AdapterResult(
                success=False,
                errors=[f"Error in generic extraction: {str(e)}"]
            )
    
    def _extract_service_manifest(self, file_path: str, content: str,
                                 repo_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract service manifest using generic heuristics."""
        
        # Extract basic information
        name = self._extract_name(file_path)
        version = self._extract_version(content)
        runtime = self._determine_runtime(file_path, content)
        domain = self._determine_domain(name, content)
        maturity = self._determine_maturity(name, content)
        
        # Extract dependencies
        dependencies = self._extract_dependencies(content)
        
        # Extract additional metadata
        additional_fields = {
            'dependencies': dependencies,
            'file_path': file_path,
            'file_size': len(content),
            'language': self._detect_language(file_path, content),
            'frameworks': self._detect_frameworks(content),
            'has_tests': self._detect_tests(file_path, content),
            'has_docs': self._detect_docs(file_path, content),
            'has_ci': self._detect_ci(file_path, content)
        }
        
        # Add repository metadata if available
        if repo_metadata:
            additional_fields.update({
                'repo': repo_metadata.get('repo_url'),
                'path': repo_metadata.get('path', ''),
                'last_commit': repo_metadata.get('last_commit')
            })
        
        return self._generate_manifest(
            name=name,
            version=version,
            domain=domain,
            maturity=maturity,
            runtime=runtime,
            additional_fields=additional_fields
        )
    
    def _extract_name(self, file_path: str) -> str:
        """Extract service name from file path."""
        # Get the directory name or filename
        path_parts = file_path.split('/')
        
        # Look for service indicators in the path
        for part in reversed(path_parts):
            if part and part not in ['src', 'app', 'lib', 'bin', 'dist', 'build']:
                name = part
                break
        else:
            name = 'unknown'
        
        # Clean and normalize name
        name = re.sub(r'^254carbon-', '', name)
        name = re.sub(r'-(service|api|app|web)$', '', name)
        name = re.sub(r'^service-', '', name)
        name = re.sub(r'^api-', '', name)
        
        # Convert to service name format
        name = name.replace('-', '_')
        return name.lower()
    
    def _extract_version(self, content: str) -> str:
        """Extract version from content using heuristics."""
        # Look for version patterns in content
        version_patterns = [
            r'version\s*[:=]\s*["\']?(\d+\.\d+\.\d+)["\']?',
            r'VERSION\s*[:=]\s*["\']?(\d+\.\d+\.\d+)["\']?',
            r'__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']',
            r'version\s*=\s*["\'](\d+\.\d+\.\d+)["\']',
            r'v(\d+\.\d+\.\d+)',
            r'(\d+\.\d+\.\d+)'
        ]
        
        for pattern in version_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                # Return the first valid version found
                for match in matches:
                    if re.match(r'^\d+\.\d+\.\d+$', match):
                        return match
        
        return '1.0.0'  # Default version
    
    def _detect_language(self, file_path: str, content: str) -> str:
        """Detect programming language from file path and content."""
        file_path_lower = file_path.lower()
        
        # Check file extension
        if file_path_lower.endswith('.py'):
            return 'python'
        elif file_path_lower.endswith(('.js', '.ts', '.jsx', '.tsx')):
            return 'javascript'
        elif file_path_lower.endswith('.go'):
            return 'go'
        elif file_path_lower.endswith('.rs'):
            return 'rust'
        elif file_path_lower.endswith('.java'):
            return 'java'
        elif file_path_lower.endswith('.cs'):
            return 'csharp'
        elif file_path_lower.endswith('.php'):
            return 'php'
        elif file_path_lower.endswith('.rb'):
            return 'ruby'
        elif file_path_lower.endswith('.cpp') or file_path_lower.endswith('.cc'):
            return 'cpp'
        elif file_path_lower.endswith('.c'):
            return 'c'
        
        # Check content for language indicators
        content_lower = content.lower()
        if 'python' in content_lower or 'import ' in content_lower:
            return 'python'
        elif 'javascript' in content_lower or 'node' in content_lower:
            return 'javascript'
        elif 'go' in content_lower or 'package main' in content_lower:
            return 'go'
        elif 'rust' in content_lower or 'cargo' in content_lower:
            return 'rust'
        elif 'java' in content_lower or 'public class' in content_lower:
            return 'java'
        elif 'csharp' in content_lower or 'using System' in content_lower:
            return 'csharp'
        elif 'php' in content_lower or '<?php' in content_lower:
            return 'php'
        elif 'ruby' in content_lower or 'require ' in content_lower:
            return 'ruby'
        
        return 'unknown'
    
    def _detect_frameworks(self, content: str) -> List[str]:
        """Detect frameworks from content."""
        frameworks = []
        content_lower = content.lower()
        
        # Python frameworks
        if 'django' in content_lower:
            frameworks.append('django')
        if 'flask' in content_lower:
            frameworks.append('flask')
        if 'fastapi' in content_lower:
            frameworks.append('fastapi')
        if 'tornado' in content_lower:
            frameworks.append('tornado')
        if 'aiohttp' in content_lower:
            frameworks.append('aiohttp')
        
        # JavaScript frameworks
        if 'express' in content_lower:
            frameworks.append('express')
        if 'react' in content_lower:
            frameworks.append('react')
        if 'vue' in content_lower:
            frameworks.append('vue')
        if 'angular' in content_lower:
            frameworks.append('angular')
        if 'next' in content_lower:
            frameworks.append('next')
        
        # Go frameworks
        if 'gin' in content_lower:
            frameworks.append('gin')
        if 'fiber' in content_lower:
            frameworks.append('fiber')
        if 'echo' in content_lower:
            frameworks.append('echo')
        
        # Rust frameworks
        if 'actix' in content_lower:
            frameworks.append('actix')
        if 'rocket' in content_lower:
            frameworks.append('rocket')
        if 'warp' in content_lower:
            frameworks.append('warp')
        
        # Java frameworks
        if 'spring' in content_lower:
            frameworks.append('spring')
        if 'hibernate' in content_lower:
            frameworks.append('hibernate')
        
        return frameworks
    
    def _detect_tests(self, file_path: str, content: str) -> bool:
        """Detect if the file contains tests."""
        file_path_lower = file_path.lower()
        content_lower = content.lower()
        
        # Check file path for test indicators
        if any(pattern in file_path_lower for pattern in ['test', 'spec', 'specs']):
            return True
        
        # Check content for test indicators
        test_patterns = [
            'def test_', 'class Test', 'it(', 'describe(', 'test(', 'assert ',
            'expect(', 'should ', 'unittest', 'pytest', 'jest', 'mocha'
        ]
        
        for pattern in test_patterns:
            if pattern in content_lower:
                return True
        
        return False
    
    def _detect_docs(self, file_path: str, content: str) -> bool:
        """Detect if the file contains documentation."""
        file_path_lower = file_path.lower()
        content_lower = content.lower()
        
        # Check file path for doc indicators
        if any(pattern in file_path_lower for pattern in ['readme', 'docs', 'doc']):
            return True
        
        # Check content for doc indicators
        doc_patterns = [
            '# ', '## ', '### ', '<!--', 'docstring', 'javadoc',
            'godoc', 'rustdoc', 'sphinx', 'mkdocs'
        ]
        
        for pattern in doc_patterns:
            if pattern in content_lower:
                return True
        
        return False
    
    def _detect_ci(self, file_path: str, content: str) -> bool:
        """Detect if the file contains CI configuration."""
        file_path_lower = file_path.lower()
        content_lower = content.lower()
        
        # Check file path for CI indicators
        if any(pattern in file_path_lower for pattern in ['.github', 'ci', 'jenkins', 'travis']):
            return True
        
        # Check content for CI indicators
        ci_patterns = [
            'workflow', 'pipeline', 'build', 'test', 'deploy',
            'github actions', 'gitlab ci', 'jenkins', 'travis'
        ]
        
        for pattern in ci_patterns:
            if pattern in content_lower:
                return True
        
        return False
    
    def _extract_dependencies(self, content: str) -> Dict[str, List[str]]:
        """Extract dependencies from content using heuristics."""
        dependencies = {
            'internal': [],
            'external': []
        }
        
        # Look for import statements
        import_patterns = [
            r'import\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'from\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+import',
            r'require\(["\']([^"\']+)["\']\)',
            r'import\s+["\']([^"\']+)["\']',
            r'use\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'package\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'use\s+([a-zA-Z_][a-zA-Z0-9_]*::)',
            r'#include\s*<([^>]+)>',
            r'#include\s*"([^"]+)"'
        ]
        
        for pattern in import_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                
                # Categorize dependencies
                if match.startswith('254carbon') or match.startswith('@254carbon'):
                    dependencies['internal'].append(match)
                else:
                    dependencies['external'].append(match)
        
        # Remove duplicates
        dependencies['internal'] = list(set(dependencies['internal']))
        dependencies['external'] = list(set(dependencies['external']))
        
        return dependencies
    
    def _get_heuristics_used(self, file_path: str, content: str) -> List[str]:
        """Get list of heuristics used for extraction."""
        heuristics = []
        
        if self._detect_language(file_path, content) != 'unknown':
            heuristics.append('language_detection')
        
        if self._detect_frameworks(content):
            heuristics.append('framework_detection')
        
        if self._detect_tests(file_path, content):
            heuristics.append('test_detection')
        
        if self._detect_docs(file_path, content):
            heuristics.append('doc_detection')
        
        if self._detect_ci(file_path, content):
            heuristics.append('ci_detection')
        
        if self._extract_dependencies(content)['external']:
            heuristics.append('dependency_extraction')
        
        return heuristics
